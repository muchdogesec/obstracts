const CHANNELS = ["prod", "staging", "test"];
const KEEP_PER_CHANNEL = 3;
const DIGEST_PATTERN = /^sha256:[0-9a-f]{64}$/;
const INDEX_MEDIA_TYPES = new Set([
  "application/vnd.oci.image.index.v1+json",
  "application/vnd.docker.distribution.manifest.list.v2+json",
]);
const MANIFEST_MEDIA_TYPES = new Set([
  "application/vnd.oci.image.manifest.v1+json",
  "application/vnd.oci.artifact.manifest.v1+json",
  "application/vnd.docker.distribution.manifest.v2+json",
]);

function immutableChannel(tag) {
  const match = /^sha-(prod|staging|test)-[0-9a-f]{40}$/i.exec(tag);
  if (match) return match[1].toLowerCase();
  // Retain compatibility while old tags age out after this policy ships.
  if (/^test-sha-[0-9a-f]+$/i.test(tag)) return "test";
  return null;
}

function isReferrerFallbackTag(tag) {
  return /^sha256-[0-9a-f]{64}$/i.test(tag);
}

function normalizeVersions(versions) {
  if (!Array.isArray(versions)) {
    throw new Error("package versions response is not an array");
  }
  const ids = new Set();
  const digests = new Set();
  return versions.map((version) => {
    if (!version || typeof version !== "object" || !Number.isInteger(version.id)) {
      throw new Error("package version has an invalid id");
    }
    if (ids.has(version.id)) {
      throw new Error(`duplicate package version id ${version.id}`);
    }
    if (!DIGEST_PATTERN.test(version.name ?? "")) {
      throw new Error(`package version ${version.id} has no valid digest`);
    }
    if (digests.has(version.name)) {
      throw new Error(`multiple package versions have digest ${version.name}`);
    }
    const tags = version.metadata?.container?.tags;
    if (!Array.isArray(tags) || tags.some((tag) => typeof tag !== "string")) {
      throw new Error(`package version ${version.id} has invalid tag metadata`);
    }
    if (!Number.isFinite(Date.parse(version.created_at))) {
      throw new Error(`package version ${version.id} has invalid created_at`);
    }
    ids.add(version.id);
    digests.add(version.name);
    return { ...version, tags };
  });
}

export function selectReleaseRoots(versions) {
  const normalized = normalizeVersions(versions);
  const keep = new Set();

  for (const channel of CHANNELS) {
    const candidates = normalized.filter((version) =>
      version.tags.some(
        (tag) => tag === channel || immutableChannel(tag) === channel,
      ),
    );
    const current = candidates.filter((version) =>
      version.tags.includes(channel),
    );

    if (current.length > 1) {
      throw new Error(`multiple package versions carry the ${channel} tag`);
    }
    if (
      current.length === 1 &&
      !current[0].tags.some(
        (tag) =>
          immutableChannel(tag) === channel ||
          // Legacy prod/staging images used an unqualified sha-* tag.
          /^sha-[0-9a-f]+$/i.test(tag),
      )
    ) {
      throw new Error(`${channel} tag has no corresponding immutable SHA tag`);
    }

    candidates
      .sort((left, right) => {
        const leftCurrent = left.tags.includes(channel) ? 1 : 0;
        const rightCurrent = right.tags.includes(channel) ? 1 : 0;
        if (leftCurrent !== rightCurrent) return rightCurrent - leftCurrent;
        return Date.parse(right.created_at) - Date.parse(left.created_at);
      })
      .slice(0, KEEP_PER_CHANNEL)
      .forEach((version) => keep.add(version.id));
  }

  const unknownTagged = normalized.filter((version) =>
    version.tags.some(
      (tag) =>
        !CHANNELS.includes(tag) &&
        immutableChannel(tag) === null &&
        !isReferrerFallbackTag(tag) &&
        !/^sha-[0-9a-f]+$/i.test(tag),
    ),
  );
  if (unknownTagged.length > 0) {
    const details = unknownTagged
      .map((version) => `${version.id}: ${version.tags.join(", ")}`)
      .join("; ");
    throw new Error(`refusing to delete unrecognized tagged versions: ${details}`);
  }

  return normalized.filter((version) => keep.has(version.id));
}

function descriptorDigests(document) {
  if (!document || !Array.isArray(document.manifests)) {
    throw new Error("registry response does not contain a manifests array");
  }
  return document.manifests.map((descriptor) => {
    if (!/^sha256:[0-9a-f]{64}$/i.test(descriptor.digest ?? "")) {
      throw new Error("registry descriptor has no valid sha256 digest");
    }
    return descriptor.digest;
  });
}

function inspectManifest(document, digest) {
  if (
    !document ||
    typeof document !== "object" ||
    Array.isArray(document) ||
    document.schemaVersion !== 2 ||
    typeof document.mediaType !== "string"
  ) {
    throw new Error(`manifest ${digest} is not a valid schema-version 2 manifest`);
  }
  if (!INDEX_MEDIA_TYPES.has(document.mediaType) && !MANIFEST_MEDIA_TYPES.has(document.mediaType)) {
    throw new Error(`manifest ${digest} has unsupported media type ${document.mediaType}`);
  }
  const children = INDEX_MEDIA_TYPES.has(document.mediaType)
    ? descriptorDigests(document)
    : [];
  if (
    document.mediaType === "application/vnd.oci.artifact.manifest.v1+json" &&
    !Array.isArray(document.blobs)
  ) {
    throw new Error(`artifact manifest ${digest} has no blobs array`);
  }
  let subject = null;
  if (document.subject !== undefined) {
    subject = document.subject?.digest;
    if (!DIGEST_PATTERN.test(subject ?? "")) {
      throw new Error(`manifest ${digest} has no valid subject digest`);
    }
  }
  return { children, subject };
}

export async function planRetention(
  versions,
  { manifestForDigest, expectedChannel },
) {
  const normalized = normalizeVersions(versions);
  if (!CHANNELS.includes(expectedChannel)) {
    throw new Error(
      `EXPECTED_CHANNEL must be one of ${CHANNELS.join(", ")}`,
    );
  }
  // A package can legitimately predate one or more release channels, but the
  // workflow that just published must be able to observe exactly one moving
  // tag for its own channel before this process is allowed to plan deletions.
  const activeRoots = normalized.filter((version) =>
    version.tags.includes(expectedChannel),
  );
  if (activeRoots.length !== 1) {
    throw new Error(
      `expected exactly one package version carrying the active ${expectedChannel} tag; found ${activeRoots.length}`,
    );
  }
  const roots = selectReleaseRoots(normalized);
  const byDigest = new Map();
  const fallbackBySubject = new Map();
  for (const version of normalized) {
    byDigest.set(version.name, version);
    for (const tag of version.tags.filter(isReferrerFallbackTag)) {
      const subject = `sha256:${tag.slice("sha256-".length).toLowerCase()}`;
      if (fallbackBySubject.has(subject)) {
        throw new Error(`multiple referrer fallback indexes exist for ${subject}`);
      }
      fallbackBySubject.set(subject, version);
    }
  }

  // Inventory every manifest before deciding to delete anything. GHCR has used
  // both OCI artifact subjects and the Distribution 1.0 sha256-<subject> tag
  // convention for referrers, so registry inventory is the reliable source of
  // both representations. Incoming parent-index edges are deliberately omitted:
  // a platform manifest shared with an obsolete release must not retain that root.
  const children = new Map();
  const referrersBySubject = new Map();
  for (const version of normalized) {
    const manifest = await manifestForDigest(version.name);
    const inspected = inspectManifest(manifest, version.name);
    if (
      version.tags.some(isReferrerFallbackTag) &&
      !INDEX_MEDIA_TYPES.has(manifest.mediaType)
    ) {
      throw new Error(`fallback referrer ${version.name} is not an index`);
    }
    children.set(version.name, inspected.children);
    if (inspected.subject !== null) {
      const subject = inspected.subject;
      const referrers = referrersBySubject.get(subject) ?? [];
      referrers.push(version.name);
      referrersBySubject.set(subject, referrers);
    }
  }

  // A retained release is unusable without its transitive platform manifests,
  // provenance referrers, and fallback referrer indexes.
  const keepDigests = new Set();
  const pending = roots.map((version) => version.name);
  while (pending.length > 0) {
    const digest = pending.pop();
    if (keepDigests.has(digest)) continue;
    const version = byDigest.get(digest);
    if (!version) {
      throw new Error(`registry references unknown package version ${digest}`);
    }
    keepDigests.add(digest);
    const fallback = fallbackBySubject.get(digest);
    pending.push(
      ...(children.get(digest) ?? []),
      ...(referrersBySubject.get(digest) ?? []),
      ...(fallback ? [fallback.name] : []),
    );
  }

  const keep = normalized.filter((version) => keepDigests.has(version.name));
  const remove = normalized.filter((version) => !keepDigests.has(version.name));
  const protectedMovingTag = remove.find((version) =>
    version.tags.some((tag) => CHANNELS.includes(tag)),
  );
  if (protectedMovingTag) {
    throw new Error(
      `retention plan would delete moving channel tag on version ${protectedMovingTag.id}`,
    );
  }
  return { keep, remove };
}

async function githubRequest(path, options = {}) {
  const response = await fetch(`${process.env.GITHUB_API_URL ?? "https://api.github.com"}${path}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...options.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`${options.method ?? "GET"} ${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.status === 204 ? null : response.json();
}

export async function listVersions(owner, packageName, request = githubRequest) {
  const versions = [];
  for (let page = 1; ; page += 1) {
    const batch = await request(
      `/orgs/${encodeURIComponent(owner)}/packages/container/${encodeURIComponent(packageName)}/versions?per_page=100&page=${page}`,
    );
    if (!Array.isArray(batch)) {
      throw new Error("GitHub package versions response is not an array");
    }
    versions.push(...batch);
    if (batch.length < 100) return versions;
  }
}

const MANIFEST_ACCEPT = [
  "application/vnd.oci.image.index.v1+json",
  "application/vnd.oci.image.manifest.v1+json",
  "application/vnd.oci.artifact.manifest.v1+json",
  "application/vnd.docker.distribution.manifest.list.v2+json",
  "application/vnd.docker.distribution.manifest.v2+json",
].join(", ");

async function registryResponse(owner, packageName, suffix, accept) {
  const url = `https://ghcr.io/v2/${owner.toLowerCase()}/${packageName.toLowerCase()}/${suffix}`;
  const basic = Buffer.from(
    `${process.env.GITHUB_ACTOR}:${process.env.GITHUB_TOKEN}`,
  ).toString("base64");
  let response = await fetch(url, {
    headers: { Accept: accept, Authorization: `Basic ${basic}` },
  });

  if (response.status === 401) {
    const challenge = response.headers.get("www-authenticate") ?? "";
    const realm = /realm="([^"]+)"/.exec(challenge)?.[1];
    const service = /service="([^"]+)"/.exec(challenge)?.[1];
    const scope = /scope="([^"]+)"/.exec(challenge)?.[1];
    if (!realm || !service || !scope) {
      throw new Error(`GHCR returned an unsupported authentication challenge: ${challenge}`);
    }
    const tokenUrl = new URL(realm);
    tokenUrl.searchParams.set("service", service);
    tokenUrl.searchParams.set("scope", scope);
    const tokenResponse = await fetch(tokenUrl, {
      headers: { Authorization: `Basic ${basic}` },
    });
    if (!tokenResponse.ok) {
      throw new Error(`GHCR token request failed: ${tokenResponse.status}`);
    }
    const tokenDocument = await tokenResponse.json();
    if (typeof tokenDocument.token !== "string") {
      throw new Error("GHCR token response has no token");
    }
    response = await fetch(url, {
      headers: { Accept: accept, Authorization: `Bearer ${tokenDocument.token}` },
    });
  }

  if (!response.ok) {
    throw new Error(`reading GHCR ${suffix} failed: ${response.status}`);
  }
  return response;
}

export async function registryManifest(owner, packageName, digest) {
  const response = await registryResponse(
    owner,
    packageName,
    `manifests/${digest}`,
    MANIFEST_ACCEPT,
  );
  const responseDigest = response.headers.get("docker-content-digest");
  if (responseDigest === null) {
    throw new Error(`GHCR returned no Docker-Content-Digest for ${digest}`);
  }
  if (responseDigest.toLowerCase() !== digest.toLowerCase()) {
    throw new Error(
      `GHCR returned manifest ${responseDigest} when ${digest} was requested`,
    );
  }
  return response.json();
}

export async function deleteVersions(owner, packageName, versions, request = githubRequest) {
  for (const version of versions) {
    const tags = version.tags.length === 0 ? "untagged" : version.tags.join(",");
    console.log(`Deleting package version ${version.id} (${tags}).`);
    await request(
      `/orgs/${encodeURIComponent(owner)}/packages/container/${encodeURIComponent(packageName)}/versions/${version.id}`,
      { method: "DELETE" },
    );
  }
}

async function main() {
  const owner = process.env.GITHUB_REPOSITORY_OWNER;
  const packageName = process.env.PACKAGE_NAME;
  const expectedChannel = process.env.EXPECTED_CHANNEL;
  if (!owner || !packageName || !process.env.GITHUB_TOKEN || !process.env.GITHUB_ACTOR || !expectedChannel) {
    throw new Error("GITHUB_REPOSITORY_OWNER, PACKAGE_NAME, GITHUB_ACTOR, GITHUB_TOKEN, and EXPECTED_CHANNEL are required");
  }

  const versions = await listVersions(owner, packageName);
  const plan = await planRetention(versions, {
    manifestForDigest: (digest) => registryManifest(owner, packageName, digest),
    expectedChannel,
  });
  console.log(`Keeping ${plan.keep.length} package versions.`);
  await deleteVersions(owner, packageName, plan.remove);
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
