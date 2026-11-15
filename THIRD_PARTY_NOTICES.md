# Third-party notices and license inventory

**Status:** preliminary / incomplete  
**Last reviewed:** 2026-11-16  
**Applies to:** Stream TTS Studio source repository and the separately supplied portable runtime described in [docs/PORTABLE_RUNTIME.md](docs/PORTABLE_RUNTIME.md).

## Scope

The MIT License in the repository applies only to original Stream TTS Studio code and documentation authored for this project, unless a file says otherwise. It does not replace the license of third-party libraries, models, binaries, fonts, or other assets.

This file is an inventory of components currently known from the source tree and the owner's portable-runtime snapshot. It is not a complete Software Bill of Materials (SBOM), legal opinion, or proof that every redistribution obligation has been satisfied.

## Known components

| Component | Known version / revision | License information | Verification status |
|---|---|---|---|
| Stream TTS Studio original code | Current repository revision | MIT | See root `LICENSE`; applies only to original project work |
| CosyVoice upstream | Runtime snapshot uses CosyVoice 3 | Apache License 2.0 upstream | Upstream license identified; exact runtime revision, bundled notices and third-party/submodule closure still need inventory |
| Fun-CosyVoice3-0.5B-2512 model | Model snapshot in portable runtime | Hugging Face model card declares Apache-2.0 | Model-card metadata identified; exact downloaded revision and auxiliary model/assets still need verification |
| PyTorch | 2.7.1+cu128 | BSD-style / BSD-3-Clause metadata | Package license identified; transitive/binary notices not inventoried |
| Python | 3.10.11 portable | Python Software Foundation License | Runtime version identified; distribution files and notices should be retained |
| FFmpeg | 7.1.1, Gyan full build | Gyan states its static builds are GPLv3 | Exact binary build configuration, enabled libraries, corresponding source and redistribution materials are not yet recorded |
| CUDA / cuDNN | CUDA build 12.8; cuDNN 9.7.1 in the owner's snapshot | NVIDIA proprietary license terms | Exact redistributable files and applicable NVIDIA license texts need inventory |
| Other Python packages and native dependencies | See version snapshot in `docs/PORTABLE_RUNTIME.md` | Varies by package | Incomplete; full package/dependency inventory and each license/NOTICE remain to be collected |
| Model auxiliaries, tokenizer/text-normalization assets, fonts and other runtime assets | Portable runtime folders | Varies by component | Not fully inventoried |

## Important FFmpeg note

The owner's snapshot identifies `ffmpeg.exe` as FFmpeg 7.1.1 from Gyan's **full** build. Gyan's build page states that its static builds are licensed under GPLv3. Before redistributing that binary, the distributor must identify the exact build/configuration and comply with the applicable GPLv3 obligations, including providing the required license text, notices and corresponding source or a valid means of obtaining it. Do not assume that the Studio MIT license covers FFmpeg.

The exact `ffmpeg -buildconf` output, binary hash, source revision/archive and accompanying license materials were not included in the runtime snapshot. Therefore this repository does not yet claim that the FFmpeg redistribution checklist is complete.

## Required completion work before publishing a portable archive

1. Generate a complete inventory from the exact portable Python environment (direct and transitive Python packages, versions, license metadata).
2. Inventory every bundled executable, DLL, native library, model, tokenizer, auxiliary model, font and asset under the portable runtime.
3. Record exact source URLs and immutable revisions/hashes for components where available.
4. Copy required LICENSE, NOTICE, attribution and other license texts into the distribution in the locations required by their licenses.
5. For FFmpeg, record `-version`, `-buildconf`, binary SHA-256, exact Gyan archive/build identity, relevant source and GPLv3 compliance materials.
6. Review NVIDIA CUDA/cuDNN redistribution terms for the exact files shipped.
7. Re-run the inventory whenever the portable archive or any included component changes.

## Source references

- [CosyVoice upstream repository](https://github.com/FunAudioLLM/CosyVoice) — Apache-2.0 project licensing; verify notices and submodules for the exact revision used.
- [Fun-CosyVoice3-0.5B-2512 model card](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512) — model-card metadata declares Apache-2.0.
- [PyTorch 2.7.1 on PyPI](https://pypi.org/project/torch/2.7.1/) — BSD-style license metadata.
- [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/) — states static builds are GPLv3.
- [Python License](https://docs.python.org/3/license.html) — Python license text and terms.

**Distribution status:** the source-code MIT license is identified. The complete license compliance of the portable distribution is **not yet verified**.