"""Command line entry point: `python -m rag.cli <command>`.

    python -m rag.cli chunks --dump chunks_dump.md
    python -m rag.cli build --force
    python -m rag.cli query "Does creatine improve athletic performance?" --answer
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .config import Settings
from .pipeline import RAGPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag", description=__doc__)
    parser.add_argument("--source", help="HTML file path or URL")
    parser.add_argument("--chunk-size", type=int)
    parser.add_argument("--chunk-overlap", type=int)
    parser.add_argument("--questions", type=int, dest="questions_per_chunk",
                        help="hypothetical questions per chunk (0 disables)")
    parser.add_argument("--db-path")

    commands = parser.add_subparsers(dest="command", required=True)

    chunks = commands.add_parser("chunks", help="chunk and inspect, no API calls")
    chunks.add_argument("--dump", help="write every chunk to this file")
    chunks.add_argument("--show", type=int, default=5, help="preview N flagged chunks")

    index = commands.add_parser("build", help="chunk, augment and index")
    index.add_argument("--force", action="store_true", help="rebuild from scratch")

    query = commands.add_parser("query", help="search the index")
    query.add_argument("text")
    query.add_argument("--top-k", type=int)
    query.add_argument("--answer", action="store_true", help="also generate an answer")

    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    overrides = {
        key: value
        for key, value in vars(args).items()
        if value is not None
        and key in {"source", "chunk_size", "chunk_overlap", "questions_per_chunk", "db_path"}
    }
    return Settings.from_env(**overrides)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = RAGPipeline(settings_from_args(args))

    if pipeline.offline:
        print("No OPENROUTER_API_KEY found — using offline hash embeddings.\n")

    if args.command == "chunks":
        chunks = pipeline.chunk()
        report = pipeline.inspect(chunks)
        print(report.summary())
        if args.dump:
            print(f"\nfull dump -> {pipeline.inspector.dump(chunks, args.dump)}")
        for index in report.flagged[: args.show]:
            chunk = chunks[index]
            print(f"\n[{index}] {chunk.size} chars  {' '.join(report.flags[index])}")
            print(repr(chunk.text[:300]))

    elif args.command == "build":
        def progress(label: str, done: int, total: int) -> None:
            if done == total or done % 100 == 0:
                print(f"  {label}: {done}/{total}")

        report = pipeline.build(force=args.force, on_progress=progress)
        print(report.summary())

    elif args.command == "query":
        results = pipeline.search(args.text, top_k=args.top_k)
        if not results:
            print("No results — is the index built?")
            return 1
        print(f"\n--- {len(results)} results for: {args.text!r} ---")
        for position, hit in enumerate(results, start=1):
            print(f"\n[{position}] similarity {hit.similarity:.4f} "
                  f"| matched via {hit.match_type} | {hit.section or 'document'}")
            if hit.matched_text:
                print(f"    matched question: {hit.matched_text}")
            print(f"    {hit.text[:300]}...")
        if args.answer:
            print(f"\n--- answer ---\n{pipeline.answer(args.text, results)}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
