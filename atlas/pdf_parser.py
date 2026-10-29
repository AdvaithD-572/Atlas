"""Private subprocess entry point: bytes in, bounded page-text JSON out.

No application imports, credentials, file paths, network or external executables.
Linux enforces an address-space/CPU ceiling; Windows relies on parser bounds and
the parent wall timeout (deploy under container memory limits for hostile input).
"""

import io
import json
import logging
import sys


def main() -> int:
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    logging.disable(logging.CRITICAL)
    try:
        from pypdf import PdfReader, apply_configuration

        raw = sys.stdin.buffer.read(1_048_577)
        if len(raw) > 1_048_576 or not raw.startswith(b"%PDF-"):
            return 1
        with apply_configuration(
            maximum_declared_stream_length=8_388_608,
            array_based_stream_maximum_output_length=8_388_608,
            zlib_maximum_output_length=8_388_608,
            lzw_maximum_output_length=8_388_608,
            run_length_maximum_output_length=8_388_608,
            stream_decoding_work_maximum_length=16_777_216,
            page_tree_maximum_entries=500,
            page_tree_maximum_depth=32,
            xform_maximum_invocations_per_extraction=100,
            jbig2dec_binary=None,
        ):
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted:
                sys.stdout.buffer.write(b"encrypted")
                return 0
            if not 1 <= len(reader.pages) <= 200:
                return 1
            pages: list[str] = []
            count = 0
            for page in reader.pages:
                text = page.extract_text()
                count += len(text)
                if count > 1_048_576:
                    return 1
                pages.append(text)
            sys.stdout.buffer.write(json.dumps(pages, ensure_ascii=True).encode("ascii"))
            return 0
    except Exception:
        # The parent exposes a stable safe error; parser diagnostics may include source text.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
