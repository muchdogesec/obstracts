import assert from "node:assert/strict";
import test from "node:test";

import {
  deleteVersions,
  listVersions,
  planRetention,
  registryManifest,
  selectReleaseRoots,
} from "./cleanup-ghcr-versions.mjs";

function digest(value) {
  return `sha256:${Number(value).toString(16).padStart(64, "0")}`;
}

function version(id, createdAt, tags = [], versionDigest = digest(id)) {
  return {
    id,
    name: versionDigest,
    created_at: createdAt,
    metadata: { container: { tags } },
  };
}

function immutable(channel, character) {
  return `sha-${channel}-${character.repeat(40)}`;
}

function emptyRegistry(overrides = {}) {
  return {
    manifestForDigest: async (digest) => overrides.manifests?.[digest] ?? {
      schemaVersion: 2,
      mediaType: "application/vnd.oci.image.manifest.v1+json",
    },
  };
}

function index(manifests, extra = {}) {
  return {
    schemaVersion: 2,
    mediaType: "application/vnd.oci.image.index.v1+json",
    manifests,
    ...extra,
  };
}

test("keeps the moving tag and three newest release roots per channel", () => {
  const versions = [];
  let id = 0;
  for (const channel of ["prod", "staging", "test"]) {
    for (let day = 1; day <= 4; day += 1) {
      id += 1;
      const tags = [immutable(channel, String.fromCharCode(96 + day))];
      if (day === 4) tags.unshift(channel);
      versions.push(version(id, `2026-01-0${day}T00:00:00Z`, tags));
    }
  }

  assert.deepEqual(
    selectReleaseRoots(versions).map(({ id: keptId }) => keptId),
    [2, 3, 4, 6, 7, 8, 10, 11, 12],
  );
});

test("retains transitive manifest dependencies and OCI referrers", async () => {
  const root = digest(1);
  const platform = digest(2);
  const nested = digest(3);
  const attestation = digest(4);
  const versions = [
    version(1, "2026-01-01T00:00:00Z", ["prod", immutable("prod", "a")], root),
    version(2, "2026-01-01T00:00:00Z", [], platform),
    version(3, "2026-01-01T00:00:00Z", [], nested),
    version(4, "2026-01-01T00:00:00Z", [], attestation),
    version(5, "2025-01-01T00:00:00Z", [immutable("prod", "b")]),
    version(6, "2025-01-01T00:00:00Z"),
  ];
  const plan = await planRetention(versions, emptyRegistry({
    manifests: {
      [root]: index([{ digest: platform }]),
      [platform]: index([{ digest: nested }]),
      [attestation]: {
        schemaVersion: 2,
        mediaType: "application/vnd.oci.artifact.manifest.v1+json",
        blobs: [],
        subject: { digest: root },
      },
    },
  }));

  assert.deepEqual(plan.keep.map(({ id }) => id), [1, 2, 3, 4, 5]);
  assert.deepEqual(plan.remove.map(({ id }) => id), [6]);
});

test("retains a fallback referrer index and its children", async () => {
  const root = digest(10);
  const fallback = digest(11);
  const attestation = digest(12);
  const fallbackTag = `sha256-${root.slice("sha256:".length)}`;
  const plan = await planRetention([
    version(10, "2026-01-01T00:00:00Z", ["staging", immutable("staging", "a")], root),
    version(11, "2026-01-01T00:00:00Z", [fallbackTag], fallback),
    version(12, "2026-01-01T00:00:00Z", [], attestation),
    version(13, "2025-01-01T00:00:00Z"),
  ], emptyRegistry({
    manifests: {
      [fallback]: index([{ digest: attestation }]),
    },
  }));
  assert.deepEqual(plan.keep.map(({ id }) => id), [10, 11, 12]);
  assert.deepEqual(plan.remove.map(({ id }) => id), [13]);
});

test("does not retain an obsolete parent merely because it shares a child", async () => {
  const kept = digest(20);
  const shared = digest(21);
  const obsolete = digest(22);
  const versions = [
    version(20, "2026-01-04T00:00:00Z", ["test", immutable("test", "a")], kept),
    version(21, "2026-01-01T00:00:00Z", [], shared),
    version(22, "2025-01-01T00:00:00Z", [], obsolete),
  ];
  const plan = await planRetention(versions, emptyRegistry({
    manifests: {
      [kept]: index([{ digest: shared }]),
      [obsolete]: index([{ digest: shared }]),
    },
  }));
  assert.deepEqual(plan.keep.map(({ id }) => id), [20, 21]);
  assert.deepEqual(plan.remove.map(({ id }) => id), [22]);
});

test("deletes exact old tagged and untagged candidates", async () => {
  const versions = [
    version(1, "2026-01-01T00:00:00Z", [immutable("test", "a")]),
    version(2, "2026-01-02T00:00:00Z", [immutable("test", "b")]),
    version(3, "2026-01-03T00:00:00Z", [immutable("test", "c")]),
    version(4, "2026-01-04T00:00:00Z", ["test", immutable("test", "d")]),
    version(5, "2026-01-05T00:00:00Z"),
  ];
  const plan = await planRetention(versions, emptyRegistry());

  assert.deepEqual(plan.keep.map(({ id }) => id), [2, 3, 4]);
  assert.deepEqual(plan.remove.map(({ id }) => id), [1, 5]);
});

test("keeps a moving tag even if its timestamp is unexpectedly old", () => {
  const roots = selectReleaseRoots([
    version(1, "2026-01-01T00:00:00Z", ["prod", immutable("prod", "a")]),
    version(2, "2026-01-04T00:00:00Z", [immutable("prod", "b")]),
    version(3, "2026-01-03T00:00:00Z", [immutable("prod", "c")]),
    version(4, "2026-01-02T00:00:00Z", [immutable("prod", "d")]),
  ]);
  assert.deepEqual(roots.map(({ id }) => id), [1, 2, 3]);
});

test("supports legacy current tags during migration", () => {
  const roots = selectReleaseRoots([
    version(1, "2026-01-01T00:00:00Z", ["prod", "sha-a1"]),
    version(2, "2026-01-02T00:00:00Z", ["staging", "sha-b2"]),
    version(3, "2026-01-03T00:00:00Z", ["test", "test-sha-c3"]),
    version(4, "2025-12-01T00:00:00Z", ["sha-d4"]),
  ]);
  assert.deepEqual(roots.map(({ id }) => id), [1, 2, 3]);
});

test("paginates through more than 100 package versions", async () => {
  const pages = [
    Array.from({ length: 100 }, (_, index) => ({ id: index + 1 })),
    Array.from({ length: 100 }, (_, index) => ({ id: index + 101 })),
    Array.from({ length: 5 }, (_, index) => ({ id: index + 201 })),
  ];
  const paths = [];
  const versions = await listVersions("muchdogesec", "obstracts", async (path) => {
    paths.push(path);
    return pages.shift();
  });
  assert.equal(versions.length, 205);
  assert.deepEqual(paths.map((path) => new URL(`https://api.test${path}`).searchParams.get("page")), ["1", "2", "3"]);
});

test("deletes only supplied candidates and propagates API errors", async () => {
  const calls = [];
  await assert.rejects(
    deleteVersions("muchdogesec", "obstracts", [
      { id: 10, tags: [] },
      { id: 20, tags: [immutable("test", "a")] },
      { id: 30, tags: [] },
    ], async (path, options) => {
      calls.push([path, options]);
      if (path.endsWith("/20")) throw new Error("delete failed");
    }),
    /delete failed/,
  );
  assert.deepEqual(calls.map(([path]) => path.split("/").at(-1)), ["10", "20"]);
  assert.ok(calls.every(([, options]) => options.method === "DELETE"));
});

test("fails closed for unknown tags and inconsistent moving tags", () => {
  assert.throws(
    () => selectReleaseRoots([version(1, "2026-01-01T00:00:00Z", ["latest"])]),
    /unrecognized tagged versions/,
  );
  assert.throws(
    () => selectReleaseRoots([version(1, "2026-01-01T00:00:00Z", ["prod"])]),
    /no corresponding immutable SHA tag/,
  );
  assert.throws(
    () => selectReleaseRoots([
      version(1, "2026-01-01T00:00:00Z", ["test", immutable("test", "a")]),
      version(2, "2026-01-02T00:00:00Z", ["test", immutable("test", "b")]),
    ]),
    /multiple package versions/,
  );
});

test("fails closed when a dependency has no package version", async () => {
  const root = digest(30);
  const missing = digest(31);
  await assert.rejects(
    planRetention([
      version(1, "2026-01-01T00:00:00Z", ["prod", immutable("prod", "a")], root),
    ], emptyRegistry({
      manifests: { [root]: index([{ digest: missing }]) },
    })),
    new RegExp(`unknown package version ${missing}`),
  );
});

test("fails closed on registry errors and malformed manifests", async () => {
  const root = version(1, "2026-01-01T00:00:00Z", ["prod", immutable("prod", "a")]);
  await assert.rejects(
    planRetention([root], {
      manifestForDigest: async () => { throw new Error("registry unavailable"); },
    }),
    /registry unavailable/,
  );
  await assert.rejects(
    planRetention([root], {
      manifestForDigest: async () => null,
    }),
    /not a valid schema-version 2 manifest/,
  );
});

test("fails closed for unsafe package metadata and manifest schemas", async () => {
  const good = version(1, "2026-01-01T00:00:00Z", ["prod", immutable("prod", "a")]);
  assert.throws(
    () => selectReleaseRoots([{ ...good, id: "1" }]),
    /invalid id/,
  );
  assert.throws(
    () => selectReleaseRoots([{ ...good, name: "sha256:not-a-digest" }]),
    /no valid digest/,
  );
  assert.throws(
    () => selectReleaseRoots([{ ...good, metadata: undefined }]),
    /invalid tag metadata/,
  );
  assert.throws(
    () => selectReleaseRoots([good, { ...good }]),
    /duplicate package version id/,
  );
  assert.throws(
    () => selectReleaseRoots([good, { ...version(2, "2026-01-02T00:00:00Z"), name: good.name }]),
    /multiple package versions have digest/,
  );
  assert.throws(
    () => selectReleaseRoots([{ ...good, created_at: "not-a-date" }]),
    /invalid created_at/,
  );

  const fallback = version(
    2,
    "2026-01-01T00:00:00Z",
    [`sha256-${good.name.slice("sha256:".length)}`],
  );
  await assert.rejects(
    planRetention([good, fallback], emptyRegistry()),
    /fallback referrer .* is not an index/,
  );
  await assert.rejects(
    planRetention([good], emptyRegistry({
      manifests: {
        [good.name]: {
          schemaVersion: 2,
          mediaType: "application/vnd.oci.artifact.manifest.v1+json",
          subject: { digest: good.name },
        },
      },
    })),
    /has no blobs array/,
  );
});

test("fails closed when GHCR omits the manifest digest header", async () => {
  const requested = digest(40);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("{}", {
    headers: { "content-type": "application/vnd.oci.image.manifest.v1+json" },
  });

  try {
    await assert.rejects(
      registryManifest("muchdogesec", "obstracts", requested),
      new RegExp(`no Docker-Content-Digest for ${requested}`),
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fails closed when GHCR returns a different manifest digest", async () => {
  const requested = digest(40);
  const returned = digest(41);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("{}", {
    headers: {
      "content-type": "application/vnd.oci.image.manifest.v1+json",
      "docker-content-digest": returned,
    },
  });

  try {
    await assert.rejects(
      registryManifest("muchdogesec", "obstracts", requested),
      new RegExp(`returned manifest ${returned} when ${requested} was requested`),
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
