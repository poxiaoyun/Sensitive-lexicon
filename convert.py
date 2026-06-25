# -*- coding: utf-8 -*-

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将目录下的词库 TXT 文件转换为指定 JSON 格式。"
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default="Vocabulary",
        help="输入目录，默认：Vocabulary",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="ret",
        help="输出目录，默认：ret",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="合并所有输入文件到一个 JSON 文件中；默认每个输入文件输出一个 JSON 文件。",
    )
    parser.add_argument(
        "--merged-name",
        default="merged.json",
        help="合并模式下输出文件名，默认：merged.json",
    )
    parser.add_argument(
        "--score",
        type=int,
        default=1,
        help="默认 score，默认：1",
    )
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="保留同一文件内的重复词条；默认会去重。",
    )
    return parser.parse_args()


def read_text_with_fallback(file_path: Path) -> str:
    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
    last_error = None

    for enc in encodings:
        try:
            return file_path.read_text(encoding=enc)
        except UnicodeDecodeError as e:
            last_error = e

    raise UnicodeDecodeError(
        getattr(last_error, "encoding", "unknown"),
        getattr(last_error, "object", b""),
        getattr(last_error, "start", 0),
        getattr(last_error, "end", 1),
        f"无法解码文件: {file_path}",
    )


def clean_terms(text: str, keep_duplicates: bool) -> List[str]:
    terms: List[str] = []
    seen = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#") or line.startswith("//"):
            continue

        if keep_duplicates:
            terms.append(line)
            continue

        if line not in seen:
            seen.add(line)
            terms.append(line)

    return terms


def build_record(term: str, category: str, score: int) -> Dict:
    return {
        "term": term,
        "score": score,
        "category": category,
        "tags": [category],
        "metadata": {},
        "version": 1,
        "createdAt": "",
        "updatedAt": "",
        "updatedBy": "",
    }


def convert_file(file_path: Path, score: int, keep_duplicates: bool) -> List[Dict]:
    category = file_path.stem
    text = read_text_with_fallback(file_path)
    terms = clean_terms(text, keep_duplicates=keep_duplicates)
    return [build_record(term, category, score) for term in terms]


def write_json(file_path: Path, data: List[Dict]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_input_files(input_dir: Path) -> List[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")

    if not input_dir.is_dir():
        raise NotADirectoryError(f"输入路径不是目录: {input_dir}")

    files = sorted([p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"])
    return files


def main() -> int:
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    try:
        input_files = find_input_files(input_dir)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    if not input_files:
        print(f"[WARN] 目录中没有找到 .txt 文件: {input_dir}")
        return 0

    total_terms = 0

    if args.merge:
        merged_data: List[Dict] = []

        for file_path in input_files:
            try:
                records = convert_file(
                    file_path=file_path,
                    score=args.score,
                    keep_duplicates=args.keep_duplicates,
                )
                merged_data.extend(records)
                total_terms += len(records)
                print(f"[OK] {file_path.name} -> {len(records)} 条")
            except Exception as e:
                print(f"[ERROR] 处理文件失败 {file_path.name}: {e}", file=sys.stderr)

        merged_path = output_dir / args.merged_name
        write_json(merged_path, merged_data)
        print(f"[DONE] 已输出合并文件: {merged_path}（共 {total_terms} 条）")
    else:
        for file_path in input_files:
            try:
                records = convert_file(
                    file_path=file_path,
                    score=args.score,
                    keep_duplicates=args.keep_duplicates,
                )
                output_file = output_dir / f"{file_path.stem}.json"
                write_json(output_file, records)
                total_terms += len(records)
                print(f"[DONE] {file_path.name} -> {output_file}（{len(records)} 条）")
            except Exception as e:
                print(f"[ERROR] 处理文件失败 {file_path.name}: {e}", file=sys.stderr)

        print(f"[SUMMARY] 共处理 {len(input_files)} 个文件，输出 {total_terms} 条词条。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

