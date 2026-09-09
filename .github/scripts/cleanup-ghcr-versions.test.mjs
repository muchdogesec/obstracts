import assert from "node:assert/strict";
import test from "node:test";

import {
  assertNoKeptManifestReferencesRemoval,
  planRetention,
} from "./cleanup-ghcr-versions.mjs";

function version(id, createdAt, tags = []) {
  return {
    id,
    created_at: createdAt,
    metadata: { container: { tags } },
  };
}

test("keeps the moving tag and three newest releases per channel", () => {
  const versions = [
    version(1, "2026-01-01T00:00:00Z", ["sha-prod-1"]),
    version(2, "2026-01-02T00:00:00Z", ["sha-prod-2"]),
    version(3, "2026-01-03T00:00:00Z", ["sha-prod-3"]),
    version(4, "2026-01-04T00:00:00Z", ["prod", "sha-prod-4"]),
    version(5, "2026-01-01T00:00:00Z", ["sha-staging-1"]),
    version(6, "2026-01-02T00:00:00Z", ["sha-staging-2"]),
    version(7, "2026-01-03T00:00:00Z", ["sha-staging-3"]),
    version(8, "2026-01-04T00:00:00Z", ["staging", "sha-staging-4"]),
    version(9, "2026-01-01T00:00:00Z", ["sha-test-1"]),
    version(10, "2026-01-02T00:00:00Z", ["sha-test-2"]),
    version(11, "2026-01-03T00:00:00Z", ["sha-test-3"]),
    version(12, "2026-01-04T00:00:00Z", ["test", "sha-test-4"]),
  ];

  const plan = planRetention(versions);
  assert.deepEqual(
    plan.keep.map(({ id }) => id),
    [2, 3, 4, 6, 7, 8, 10, 11, 12],
  );
  assert.deepEqual(plan.remove.map(({ id }) => id), [1, 5, 9]);
});

test("deletes every untagged version, including attestations", () => {
  const plan = planRetention([
    version(1, "2026-01-01T00:00:00Z", ["test", "sha-test-1"]),
    version(2, "2026-01-02T00:00:00Z"),
    version(3, "2026-01-03T00:00:00Z"),
  ]);

  assert.deepEqual(plan.keep.map(({ id }) => id), [1]);
  assert.deepEqual(plan.remove.map(({ id }) => id), [2, 3]);
});

test("refuses to delete an untagged manifest referenced by a kept tag", () => {
  const kept = version(1, "2026-01-01T00:00:00Z", ["prod", "sha-prod-1"]);
  kept.name = "sha256:kept";
  const child = version(2, "2026-01-01T00:00:00Z");
  child.name = "sha256:child";
  const plan = { keep: [kept], remove: [child] };

  assert.throws(
    () =>
      assertNoKeptManifestReferencesRemoval(
        plan,
        new Map([["sha256:kept", { manifests: [{ digest: "sha256:child" }] }]]),
      ),
    /kept manifest sha256:kept references it/,
  );
});

test("keeps a moving tag even if its timestamp is unexpectedly old", () => {
  const plan = planRetention([
    version(1, "2026-01-01T00:00:00Z", ["prod", "sha-prod-1"]),
    version(2, "2026-01-04T00:00:00Z", ["sha-prod-2"]),
    version(3, "2026-01-03T00:00:00Z", ["sha-prod-3"]),
    version(4, "2026-01-02T00:00:00Z", ["sha-prod-4"]),
  ]);

  assert.deepEqual(plan.keep.map(({ id }) => id), [1, 2, 3]);
  assert.deepEqual(plan.remove.map(({ id }) => id), [4]);
});

test("supports the legacy current tags during migration", () => {
  const plan = planRetention([
    version(1, "2026-01-01T00:00:00Z", ["prod", "sha-a1"]),
    version(2, "2026-01-02T00:00:00Z", ["staging", "sha-b2"]),
    version(3, "2026-01-03T00:00:00Z", ["test", "test-sha-c3"]),
    version(4, "2025-12-01T00:00:00Z", ["sha-d4"]),
  ]);

  assert.deepEqual(plan.keep.map(({ id }) => id), [1, 2, 3]);
  assert.deepEqual(plan.remove.map(({ id }) => id), [4]);
});

test("fails closed for an unknown tagged image", () => {
  assert.throws(
    () => planRetention([version(1, "2026-01-01T00:00:00Z", ["latest"])]),
    /unrecognized tagged versions/,
  );
});

test("fails closed when a moving tag has no immutable tag", () => {
  assert.throws(
    () => planRetention([version(1, "2026-01-01T00:00:00Z", ["prod"])]),
    /no corresponding immutable SHA tag/,
  );
});

test("fails closed when a moving tag appears on multiple versions", () => {
  assert.throws(
    () =>
      planRetention([
        version(1, "2026-01-01T00:00:00Z", ["test", "sha-test-1"]),
        version(2, "2026-01-02T00:00:00Z", ["test", "sha-test-2"]),
      ]),
    /multiple package versions/,
  );
});
