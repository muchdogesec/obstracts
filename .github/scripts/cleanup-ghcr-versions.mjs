const CHANNELS = ["prod", "staging", "test"];
const KEEP_PER_CHANNEL = 3;

function immutableChannel(tag) {
  const match = /^sha-(prod|staging|test)-[0-9a-f]+$/i.exec(tag);
  if (match) return match[1].toLowerCase();

  // Retain compatibility with images published before channel-qualified tags.
  if (/^test-sha-[0-9a-f]+$/i.test(tag)) return "test";
  return null;
}

export function planRetention(versions) {
  const normalized = versions.map((version) => ({
    ...version,
    tags: version.metadata?.container?.tags ?? [],
  }));
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
      throw new Error(
        `${channel} tag has no corresponding immutable SHA tag`,
      );
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
        !/^sha-[0-9a-f]+$/i.test(tag),
    ),
  );
  if (unknownTagged.length > 0) {
    const details = unknownTagged
      .map((version) => `${version.id}: ${version.tags.join(", ")}`)
      .join("; ");
    throw new Error(`refusing to delete unrecognized tagged versions: ${details}`);
  }

  const remove = normalized.filter((version) => !keep.has(version.id));
  const protectedMovingTag = remove.find((version) =>
    version.tags.some((tag) => CHANNELS.includes(tag)),
  );
  if (protectedMovingTag) {
    throw new Error(
      `retention plan would delete moving channel tag on version ${protectedMovingTag.id}`,
    );
  }

  return {
    keep: normalized.filter((version) => keep.has(version.id)),
    remove,
  };
}

export function assertNoKeptManifestReferencesRemoval(plan, manifestsByDigest) {
  const removableByDigest = new Map(
    plan.remove.map((version) => [version.name, version]),
  );

  for (const [digest, manifest] of manifestsByDigest) {
    for (const descriptor of manifest.manifests ?? []) {
      const removable = removableByDigest.get(descriptor.digest);
      if (removable) {
        throw new Error(
          `refusing to delete untagged package version ${removable.id} (${descriptor.digest}); kept manifest ${digest} references it`,
        );
      }
    }
  }
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

async function listVersions(owner, packageName) {
  const versions = [];
  for (let page = 1; ; page += 1) {
    const batch = await githubRequest(
      `/orgs/${encodeURIComponent(owner)}/packages/container/${encodeURIComponent(packageName)}/versions?per_page=100&page=${page}`,
    );
    versions.push(...batch);
    if (batch.length < 100) return versions;
  }
}

async function registryManifest(owner, packageName, digest) {
  const url = `https://ghcr.io/v2/${owner.toLowerCase()}/${packageName.toLowerCase()}/manifests/${digest}`;
  const accept = [
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
  ].join(", ");
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
    const { token } = await tokenResponse.json();
    response = await fetch(url, {
      headers: { Accept: accept, Authorization: `Bearer ${token}` },
    });
  }

  if (!response.ok) {
    throw new Error(`reading GHCR manifest ${digest} failed: ${response.status}`);
  }
  return response.json();
}

async function validateRegistryReferences(owner, packageName, plan) {
  const manifests = new Map();
  for (const version of plan.keep) {
    manifests.set(
      version.name,
      await registryManifest(owner, packageName, version.name),
    );
  }
  assertNoKeptManifestReferencesRemoval(plan, manifests);
}

async function main() {
  const owner = process.env.GITHUB_REPOSITORY_OWNER;
  const packageName = process.env.PACKAGE_NAME;
  if (!owner || !packageName || !process.env.GITHUB_TOKEN || !process.env.GITHUB_ACTOR) {
    throw new Error("GITHUB_REPOSITORY_OWNER, PACKAGE_NAME, GITHUB_ACTOR, and GITHUB_TOKEN are required");
  }

  const versions = await listVersions(owner, packageName);
  const plan = planRetention(versions);
  await validateRegistryReferences(owner, packageName, plan);
  console.log(`Keeping ${plan.keep.length} tagged package versions.`);

  for (const version of plan.remove) {
    const tags = version.tags.length === 0 ? "untagged" : version.tags.join(",");
    console.log(`Deleting package version ${version.id} (${tags}).`);
    await githubRequest(
      `/orgs/${encodeURIComponent(owner)}/packages/container/${encodeURIComponent(packageName)}/versions/${version.id}`,
      { method: "DELETE" },
    );
  }
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
