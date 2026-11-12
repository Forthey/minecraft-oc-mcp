"""Структурный валидатор markdown-скиллов из каталога skills/.

Проверяет frontmatter, длину тела, относительные ссылки, а также то, что скиллы
ссылаются только на tools и коды ошибок из skills/references/tool-contract.md.

Запуск: python tools/validate_skills.py [root]
Код возврата 0, если ошибок нет, иначе 1 и список ошибок в stdout.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ALL_ERROR_CODES = {
    "BLOCKED", "NO_PATH", "OUT_OF_RANGE", "NO_ITEM", "INVENTORY_FULL", "NO_ENERGY",
    "TOOL_BROKEN", "CANT_PLACE", "UNKNOWN_ITEM", "NO_RECIPE", "TIMEOUT", "CONNECTION_LOST",
    "UNSUPPORTED", "NO_PROVIDER", "UNKNOWN",
}

# Встроенные tools самих агентов. Они не входят в MCP-контракт робота, но скиллы
# могут на них ссылаться.
AGENT_TOOLS = {"WebSearch", "WebFetch", "Task", "webfetch"}

JOURNAL_LINE_RE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\] phase=\S+ stage=\S+ role=\S+ "
    r"status=(DONE|PARTIAL|BLOCKED|FAILED) delta=\S+ calls=\d+ budget=\S+$"
)

ALLOWED_FIELDS = {"name", "description"}
NAME_RE = re.compile(r"^[a-z0-9-]+$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TOOL_CALL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)\(")
CODE_TOKEN_RE = re.compile(r"`([A-Z][A-Z_]+)`")
# Похоже на код ошибки, если в токене есть подчёркивание. Так отсекаются PASS,
# FAIL, DONE и прочие слова капсом, которые кодами не являются.
ERROR_LIKE_RE = re.compile(r"^[A-Z]+_[A-Z_]+$")
FENCE_RE = re.compile(r"```journal\n(.*?)\n```", re.S)


@dataclass
class Skill:
    """Разобранный SKILL.md: поля frontmatter и тело."""

    name: str
    description: str
    body: str
    path: Path
    fields: dict


def load_skill(path: Path) -> Skill:
    """Читает SKILL.md и разбирает frontmatter.

    Бросает ValueError, если файл не начинается с блока frontmatter между "---".
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"{path}: unterminated frontmatter")
    fields = yaml.safe_load(text[4:end]) or {}
    if not isinstance(fields, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")
    return Skill(
        name=str(fields.get("name", "")),
        description=str(fields.get("description", "")),
        body=text[end + 5:],
        path=path,
        fields=fields,
    )


def check_frontmatter(skill: Skill) -> list[str]:
    """Возвращает ошибки frontmatter: лишние поля, имя, формат description."""
    errors = []
    extra = set(skill.fields) - ALLOWED_FIELDS
    if extra:
        errors.append(f"{skill.path}: unexpected frontmatter fields {sorted(extra)}")
    dirname = skill.path.parent.name
    if skill.name != dirname:
        errors.append(f"{skill.path}: name '{skill.name}' does not match directory '{dirname}'")
    if not NAME_RE.match(skill.name):
        errors.append(f"{skill.path}: name must match [a-z0-9-]+")
    if not skill.description.startswith("Use when"):
        errors.append(f"{skill.path}: description must start with 'Use when'")
    if len(skill.description) > 1024:
        errors.append(f"{skill.path}: description longer than 1024 chars")
    return errors


def check_body_length(skill: Skill, max_lines: int = 500) -> list[str]:
    """Возвращает ошибку, если тело скилла длиннее max_lines строк."""
    lines = skill.body.rstrip("\n").count("\n") + 1
    if lines > max_lines:
        return [f"{skill.path}: body has {lines} lines, max {max_lines}"]
    return []


def check_links(md_path: Path) -> list[str]:
    """Возвращает ошибки для относительных ссылок, ведущих на несуществующие файлы.

    Внешние ссылки (http, https, mailto) и чистые якоря "#..." не проверяются.
    Якорь после пути отбрасывается, проверяется только существование файла.
    """
    errors = []
    for target in LINK_RE.findall(md_path.read_text(encoding="utf-8")):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0]
        if not (md_path.parent / file_part).exists():
            errors.append(f"{md_path}: broken link '{target}'")
    return errors


def check_links_stay_inside(md_path: Path, skills_root: Path) -> list[str]:
    """Возвращает ошибки для относительных ссылок, ведущих за пределы skills_root.

    При установке в агента копируется только каталог skills, поэтому ссылка
    наружу ломается, даже если файл в репозитории существует.
    """
    errors = []
    root = skills_root.resolve()
    for target in LINK_RE.findall(md_path.read_text(encoding="utf-8")):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        resolved = (md_path.parent / target.split("#", 1)[0]).resolve()
        if not resolved.is_relative_to(root):
            errors.append(f"{md_path}: link '{target}' leaves {skills_root.name}/")
    return errors


def contract_tools(contract_md: Path) -> set[str]:
    """Возвращает имена tools, объявленных в строках таблиц контракта."""
    names = set()
    for line in contract_md.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("|"):
            names.update(TOOL_CALL_RE.findall(line))
    return names


def contract_error_codes(contract_md: Path) -> set[str]:
    """Возвращает коды ошибок из секции "## Error codes" контракта."""
    text = contract_md.read_text(encoding="utf-8")
    start = text.find("## Error codes")
    if start == -1:
        return set()
    rest = text[start + len("## Error codes"):]
    end = rest.find("\n## ")
    return set(CODE_TOKEN_RE.findall(rest if end == -1 else rest[:end]))


def referenced_tools(text: str, known: set[str]) -> set[str]:
    """Возвращает вызовы вида `name(` из текста, которых нет ни в known, ни в AGENT_TOOLS."""
    return set(TOOL_CALL_RE.findall(text)) - known - AGENT_TOOLS


def referenced_error_codes(text: str) -> set[str]:
    """Возвращает токены, похожие на коды ошибок, но отсутствующие в ALL_ERROR_CODES."""
    tokens = set(CODE_TOKEN_RE.findall(text))
    return {t for t in tokens if ERROR_LIKE_RE.match(t) and t not in ALL_ERROR_CODES}


def check_journal_blocks(md_path: Path) -> list[str]:
    """Возвращает ошибки для строк в блоках ```journal, не подходящих под JOURNAL_LINE_RE."""
    errors = []
    for block in FENCE_RE.findall(md_path.read_text(encoding="utf-8")):
        for line in block.splitlines():
            if line.strip() and not JOURNAL_LINE_RE.match(line):
                errors.append(f"{md_path}: bad journal line '{line}'")
    return errors


def validate_repo(root: Path) -> list[str]:
    """Запускает все проверки для root/skills и возвращает список ошибок.

    Если контракта ещё нет, проверки имён tools и кодов ошибок пропускаются.
    """
    errors = []
    skills_dir = root / "skills"
    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    ref_files = sorted((skills_dir / "references").glob("*.md"))
    contract = skills_dir / "references" / "tool-contract.md"
    # Tools сервера memory описаны отдельно от контракта робота.
    memory_md = skills_dir / "references" / "memory.md"

    for path in skill_files:
        try:
            skill = load_skill(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        errors += check_frontmatter(skill)
        errors += check_body_length(skill)
    for path in skill_files + ref_files:
        errors += check_links(path)
        errors += check_links_stay_inside(path, skills_dir)

    if contract.exists():
        known = contract_tools(contract) | (contract_tools(memory_md) if memory_md.exists() else set())
        declared_codes = contract_error_codes(contract)
        if declared_codes != ALL_ERROR_CODES:
            errors.append(f"{contract}: error codes differ from ALL_ERROR_CODES")
        for path in skill_files + ref_files:
            if path in (contract, memory_md):
                continue
            text = path.read_text(encoding="utf-8")
            for name in sorted(referenced_tools(text, known)):
                errors.append(f"{path}: unknown tool '{name}'")
            for code in sorted(referenced_error_codes(text)):
                errors.append(f"{path}: unknown error code '{code}'")

    orchestrator = skills_dir / "oc-orchestrator" / "SKILL.md"
    if orchestrator.exists():
        errors += check_journal_blocks(orchestrator)
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    errors = validate_repo(root)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
