# -*- coding: utf-8 -*-

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict


# === 评分逻辑：1-10 分制 ===
# 类别基线分（按法律/平台风险等级，1=低风险，10=极高风险）
CATEGORY_BASELINE: Dict[str, int] = {
    "暴恐词库": 9,
    "涉枪涉爆": 10,
    "反动词库": 9,
    "政治类型": 9,
    "色情词库": 7,
    "色情类型": 7,
    "贪腐词库": 8,
    "GFW补充词库": 8,
    "网易前端过滤敏感词库": 7,
    "零时-Tencent": 7,
    "新思想启蒙": 6,
    "民生词库": 5,
    "COVID-19词库": 5,
    "补充词库": 6,
    "广告类型": 3,
    "其他词库": 4,
    "非法网址": 5,
}
DEFAULT_BASELINE = 5

# 各类别高危关键词（命中 +2，cap 10）
CATEGORY_BOOST_WORDS: Dict[str, List[str]] = {
    "色情词库": ["操", "逼", "奸", "肏", "做爱", "性交", "群交", "轮奸", "强奸", "嫖", "鸡奸"],
    "色情类型": ["操", "逼", "奸", "肏", "做爱", "性交", "群交", "轮奸", "强奸", "嫖", "鸡奸"],
    "涉枪涉爆": ["炸弹", "炸药", "火药", "雷管", "燃烧弹", "手榴弹", "弹药", "起爆", "硝酸甘油", "TNT"],
    "暴恐词库": ["法轮", "法轮功", "flg", "falungong", "恐怖", "极端", "圣战", "暴恐"],
    "反动词库": ["打倒", "推翻", "颠覆", "灭亡", "亡党", "分裂", "独立", "解放"],
    "政治类型": ["打倒", "推翻", "下台", "灭共", "亡党", "暗杀", "刺杀", "政变"],
    "贪腐词库": ["贪腐", "腐败", "贪官", "受贿", "洗钱", "权钱交易", "巨腐"],
    "广告类型": ["代购", "刷单", "兼职", "色情", "招嫖", "包夜", "全套"],
}

URL_PATTERN = re.compile(r"^(?:https?://)?[\w-]+(?:\.[\w-]+)+(?:[/:#?].*)?$")
ASCII_ONLY_PATTERN = re.compile(r"^[A-Za-z0-9._\-+:/?]+$")
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
DIGIT_OR_SYMBOL_VARIANT_PATTERN = re.compile(r"[0-9@#$%^&*_~`]")


def score_term(term: str, category: str) -> int:
    """对单条词条打 1-10 分。"""
    baseline = CATEGORY_BASELINE.get(category, DEFAULT_BASELINE)

    # URL/域名：分数固定为 5（无语义严重度，按风险中等处理）
    if URL_PATTERN.match(term.strip()):
        return 5

    score = baseline

    # 修正 1：纯 ASCII 短代号、长度 ≤ 3，误判风险高 → -2
    if ASCII_ONLY_PATTERN.match(term) and len(term) <= 3:
        score -= 2

    # 修正 2：长度 ≥ 6 的中文短语，更具体、置信度更高 → +1
    cjk_count = len(CJK_PATTERN.findall(term))
    if cjk_count >= 6:
        score += 1

    # 修正 3：含数字/符号谐音变体（如 9风、fl功、十7大）→ +1（规避变体，故意为之）
    if DIGIT_OR_SYMBOL_VARIANT_PATTERN.search(term) and CJK_PATTERN.search(term):
        score += 1

    # 修正 4：长度 ≥ 8 的长短语（多见于具体描述、教唆）→ +1
    if len(term) >= 8:
        score += 1

    # 加权：高危关键词命中 → +2
    boost_words = CATEGORY_BOOST_WORDS.get(category, [])
    if boost_words:
        term_lower = term.lower()
        for kw in boost_words:
            if kw.lower() in term_lower:
                score += 2
                break  # 命中一次即可

    # clamp 到 [1, 10]
    return max(1, min(10, score))


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
        default=None,
        help="固定分数（1-10）；不指定时按类别+规则自动评分。",
    )
    parser.add_argument(
        "--score-mode",
        choices=["auto", "fixed"],
        default="auto",
        help="评分模式：auto=自动（默认），fixed=使用 --score 指定的固定分数。",
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


def convert_file(file_path: Path, score_mode: str, fixed_score, keep_duplicates: bool) -> List[Dict]:
    category = file_path.stem
    text = read_text_with_fallback(file_path)
    terms = clean_terms(text, keep_duplicates=keep_duplicates)
    records = []
    for term in terms:
        if score_mode == "fixed" and fixed_score is not None:
            s = fixed_score
        else:
            s = score_term(term, category)
        records.append(build_record(term, category, s))
    return records


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
                    score_mode=args.score_mode,
                    fixed_score=args.score,
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
                    score_mode=args.score_mode,
                    fixed_score=args.score,
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

