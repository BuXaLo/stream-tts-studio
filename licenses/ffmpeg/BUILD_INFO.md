# Gyan FFmpeg 7.1.1 Full Build — source and build information

This directory records the exact Gyan FFmpeg binary used by the Stream TTS Studio portable runtime and the source-location information supplied by the build maintainer.

## Binary identity

- Distribution: Gyan FFmpeg 7.1.1 Full Build
- Version string: `7.1.1-full_build-www.gyan.dev`
- Platform/build: 64-bit static Windows build
- Official archive: [ffmpeg-7.1.1-full_build.zip](https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-full_build.zip)
- Release: [Gyan FFmpeg 7.1.1](https://github.com/GyanD/codexffmpeg/releases/tag/7.1.1)
- Archive SHA-256: `D760E1B3574402ED18B4865851F87D87E73965A982E6453212DF8621FED1C508`
- FFmpeg source revision reported for the release: `db69d06eee`
- Bundled executable SHA-256: `B1383F5D07470D503EDECDAEE4BDDC5891E986E916A698299B357F79CFE445FD`

The archive checksum was matched against the published checksum, and the extracted `bin/ffmpeg.exe` hash was matched against the executable in the local portable runtime. These checks identify the archive and executable; they do not by themselves prove source completeness or license compliance.

## Build configuration recorded from the official archive

```text
--enable-gpl
--enable-version3
--enable-static
```

The official archive includes `README.txt` and `LICENSE`. The portable runtime also contains `cosyvoice3/tools/LICENSE.GPL.txt`; keep this license text alongside the FFmpeg executable in every redistributed portable package.

## Maintainer-provided dependency manifest

The unmodified manifest supplied by Gyan is stored in [ffmpeg-7.1.1-full_build-manifest.txt](ffmpeg-7.1.1-full_build-manifest.txt).

In his email, Gyan stated that the manifest provides dependency details, repository URLs and commit hashes; source for each dependency can be obtained from the listed URL and hash. He also stated that no functional patches were applied and that the standard build instructions for each dependency in its repository are sufficient.

Gyan additionally cautioned that strings embedded in EXE/DLL files which mention a library do not, by themselves, prove that the library object is present in the FFmpeg binaries.

The manifest is retained verbatim as received. It is a source-location/build-dependency record, not a copy of the dependency source trees and not, by itself, proof that every listed item is linked into the distributed executable. License terms and notices for each actual component remain those of their respective upstream projects/packages.

## Obtaining the corresponding source

1. Use the repository URL and exact commit hash recorded for each source dependency in the manifest.
2. For MSYS2 packages, use the package names and exact package versions in the manifest; the manifest points to [MSYS2 package information](https://packages.msys2.org/packages/).
3. Preserve the upstream license and copyright notices supplied by each source repository/package.
4. Consult the upstream build instructions at the pinned revision. Gyan stated that no functional patches were applied and that the standard dependency build instructions are sufficient.
5. For FFmpeg itself, use the source revision recorded above and the official FFmpeg build/configuration information.

The manifest does not contain the source trees themselves. Availability of every pinned repository revision/package and the completeness of the build scripts/toolchain materials have not yet been independently re-fetched and reproduced by this project. Do not describe this record as an independently reproducible build.

## License

Gyan identifies this Full Build as GPLv3. The full GPLv3 text is available from the [Free Software Foundation](https://www.gnu.org/licenses/gpl-3.0.html). The portable distribution must include the GPL text already supplied with the runtime (`tools/LICENSE.GPL.txt`) and must retain it when redistributing FFmpeg.

This file is a maintainer record, not legal advice. Before publishing a portable release, make the corresponding-source information available to recipients from a stable location next to the binary download, and verify that the source references and required build materials remain accessible.
