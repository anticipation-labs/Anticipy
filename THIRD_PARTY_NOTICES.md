# Third-party notices

Anticipy is licensed under the MIT License (see `LICENSE`). The following
third-party code is vendored into this tree and keeps its own license, which
governs those files.

## Opus 1.2.1 (pendant firmware)

`firmware/source/src/lib/opus-1.2.1/` holds source files from the Opus audio
codec, version 1.2.1 (the CELT and SILK components and their ARM variants),
compiled into the pendant firmware by `firmware/source/CMakeLists.txt`. Those
files are copyright Xiph.Org Foundation, CSIRO, Skype Limited, and the other
holders named in each file, and are distributed under their three-clause
BSD-style license. The vendored tree carries **no separate `COPYING` file**;
the full license text is reproduced in the header of each source file, and
those headers must be preserved when the files are copied or modified.

## Cloudflare Containers SDK (spike)

`migration/spike/containers-sdk/node_modules/@cloudflare/containers/` is a
deliberately vendored copy of the `@cloudflare/containers` package, version
0.3.7, kept tracked so the spike is reproducible without a registry. Its
`package.json` declares the license `MIT OR Apache-2.0`, and its `README.md`
is the package's own.

## Everything else

All other dependencies are fetched at install or build time from their
registries under the versions pinned in `migration/workers/package-lock.json`,
`migration/workers/brain/package-lock.json`, and the pip installs named in
`.github/workflows/` and `brain/Dockerfile`; they are not vendored and their
licenses are not reproduced here.
