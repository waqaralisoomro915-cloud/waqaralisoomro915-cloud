"""Refresh README cards from public GitHub repositories; Python standard library only."""
import html
import json
import os
import re
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

START = "<!-- REPOSITORY-CARDS:START -->"
END = "<!-- REPOSITORY-CARDS:END -->"


def replace_section(readme, block):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("Expected exactly one repository-card marker pair")
    before, remaining = readme.split(START)
    _, after = remaining.split(END)
    return before + START + "\n" + block + "\n" + END + after


def short(value, width):
    return textwrap.shorten(value.strip(), width=width, placeholder="…")


def describe(value):
    lines = textwrap.wrap(value or "Explore the source code and project documentation.", width=34)
    if len(lines) > 2:
        lines[1] = short(" ".join(lines[1:]), 34)
    return (lines + ["", ""])[:2]


def public_repositories(fetch, owner):
    result = []
    page = 1
    while True:
        batch = fetch("/users/" + urllib.parse.quote(owner, safe="") +
                      "/repos?type=owner&per_page=100&page=" + str(page))
        for repo in batch:
            if not repo.get("private", True) and repo["owner"]["login"].lower() == owner.lower():
                result.append(repo)
        if len(batch) < 100:
            break
        page += 1
    return result


def render(template, repo, config, index):
    override = config.get(repo["name"], {})
    title = short(override.get("title", repo["name"].replace("_", " ").replace("-", " ")), 25)
    label = override.get("label", "FORK" if repo.get("fork") else "PROJECT")
    if repo.get("archived"):
        label = "ARCHIVED"
    lines = override.get("lines") or describe(repo.get("description"))
    values = {
        "TITLE": title,
        "DESCRIPTION": " ".join(lines) + " Open repository.",
        "LABEL": label,
        "INDEX": str(index + 1).zfill(2),
        "LINE1": lines[0],
        "LINE2": lines[1],
        "STACK": override.get("stack") or repo.get("language") or "Repository",
        "TITLE_SIZE": "17" if len(title) > 18 else "20",
        "COLOR": "#60caff" if index % 2 else "#47efb5",
    }
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", html.escape(value, quote=True))
    if "{{" in template:
        raise ValueError("Unresolved card template token")
    # Repository IDs are stable and avoid path collisions or unsafe names.
    path = override.get("path", "assets/cards/repo-" + str(repo["id"]) + ".svg")
    if not re.fullmatch(r"assets/cards/[A-Za-z0-9_-]+\.svg", path):
        raise ValueError("Invalid card output path")
    return path, template, title


def self_test():
    assert describe("word " * 30)[1].endswith("…")
    assert replace_section("a" + START + "old" + END + "z", "new") == "a" + START + "\nnew\n" + END + "z"
    try:
        replace_section("no markers", "new")
        raise AssertionError("Missing markers accepted")
    except ValueError:
        pass
    sample = {"id": 7, "name": "<demo>", "description": "<script> & code", "language": "Python"}
    _, rendered, _ = render("{{TITLE}} {{LINE1}}", sample, {}, 0)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    pages = [[{"private": False, "owner": {"login": "me"}}] * 100,
             [{"private": True, "owner": {"login": "me"}},
              {"private": False, "owner": {"login": "else"}},
              {"private": False, "owner": {"login": "me"}}]]
    calls = []
    def fetch(path):
        calls.append(path)
        return pages[len(calls)-1]
    assert len(public_repositories(fetch, "me")) == 101 and len(calls) == 2


def main():
    self_test()
    owner = os.environ["GITHUB_REPOSITORY_OWNER"]
    profile = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    def fetch(path):
        request = urllib.request.Request("https://api.github.com" + path, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "profile-repository-cards",
        })
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    repos = public_repositories(fetch, owner)
    if not repos:
        raise RuntimeError("No public repositories returned; refusing to erase the gallery")
    config = json.loads(Path("scripts/card-overrides.json").read_text(encoding="utf-8"))
    priority = {name: i for i, name in enumerate(config)}
    repos.sort(key=lambda repo: (priority.get(repo["name"], len(priority)), repo["name"].casefold()))
    template = Path("scripts/repository-card.svg.template").read_text(encoding="utf-8")
    raw = "https://raw.githubusercontent.com/" + profile + "/main/"
    cards = []
    Path("assets/cards").mkdir(parents=True, exist_ok=True)
    for index, repo in enumerate(repos):
        path, svg, title = render(template, repo, config, index)
        Path(path).write_text(svg, encoding="utf-8")
        cards.append('<td width="50%"><a href="' + html.escape(repo["html_url"], quote=True) +
                     '"><img src="' + raw + path + '" width="100%" alt="' +
                     html.escape(title + " — open repository", quote=True) + '" /></a></td>')
    rows = []
    for offset in range(0, len(cards), 2):
        cells = cards[offset:offset + 2]
        if len(cells) == 1:
            cells.append('<td width="50%"></td>')
        rows.append("<tr>\n" + "\n".join(cells) + "\n</tr>")
    block = "<table>\n" + "\n".join(rows) + "\n</table>\n\n"
    block += "<sub>" + str(len(repos)) + " public repositories · refreshed daily</sub>"
    readme = Path("README.md")
    updated = replace_section(readme.read_text(encoding="utf-8"), block)
    readme.write_text(updated, encoding="utf-8")
    print("Verified checks and generated", len(repos), "public repository cards.")


if __name__ == "__main__":
    main()
