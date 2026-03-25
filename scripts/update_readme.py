#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime


README_PATH = "README.md"
BLOG_START = "<!-- BLOG-POST-LIST:START -->"
BLOG_END = "<!-- BLOG-POST-LIST:END -->"
FEATURED_START = "<!-- FEATURED-PROJECTS:START -->"
FEATURED_END = "<!-- FEATURED-PROJECTS:END -->"
DEFAULT_USERNAME = "polunzh"
DEFAULT_FEED_URL = "https://polunzh.com/rss.xml"
USER_AGENT = "Mozilla/5.0 (GitHub Actions; polunzh/readme-updater)"


def fetch_text(url, *, headers=None, data=None):
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8")


def fetch_latest_blog_post(feed_url):
    feed = fetch_text(feed_url)
    root = ET.fromstring(feed)
    item = root.find(".//item")
    if item is None:
        raise RuntimeError("RSS feed does not contain any items")

    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    pub_date = item.findtext("pubDate")
    date = ""
    if pub_date:
        date = parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")

    return f"* [{title}]({link}) ({date})"


def fetch_featured_projects(username, token, limit=6):
    query = """
    query($login: String!, $limit: Int!) {
      user(login: $login) {
        pinnedItems(first: $limit, types: REPOSITORY) {
          nodes {
            ... on Repository {
              name
              description
              url
            }
          }
        }
      }
    }
    """
    payload = json.dumps(
        {
            "query": query,
            "variables": {"login": username, "limit": limit},
        }
    ).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }
    response_text = fetch_text(
        "https://api.github.com/graphql",
        headers=headers,
        data=payload,
    )
    payload = json.loads(response_text)

    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL returned errors: {payload['errors']}")

    nodes = payload["data"]["user"]["pinnedItems"]["nodes"]
    projects = []
    for node in nodes:
        if not node:
            continue
        description = normalize_whitespace(node.get("description") or "No description provided.")
        projects.append(
            f"* **[{node['name']}]({node['url']})** - {description}"
        )

    if not projects:
        raise RuntimeError("GitHub returned no pinned repositories")

    return "\n".join(projects)


def normalize_whitespace(text):
    return " ".join(text.split())


def replace_section(content, start_marker, end_marker, replacement):
    pattern = rf"({re.escape(start_marker)}).*?({re.escape(end_marker)})"
    updated, count = re.subn(
        pattern,
        f"{start_marker}\n{replacement}\n{end_marker}",
        content,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError(f"Could not find section markers: {start_marker} / {end_marker}")
    return updated


def main():
    username = os.environ.get("PROFILE_USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER") or DEFAULT_USERNAME
    feed_url = os.environ.get("BLOG_FEED_URL") or DEFAULT_FEED_URL
    token = os.environ.get("GITHUB_TOKEN")

    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to fetch pinned repositories")

    with open(README_PATH, "r", encoding="utf-8") as file:
        readme = file.read()

    featured_projects = fetch_featured_projects(username, token)
    latest_blog_post = fetch_latest_blog_post(feed_url)

    updated = replace_section(readme, FEATURED_START, FEATURED_END, featured_projects)
    updated = replace_section(updated, BLOG_START, BLOG_END, latest_blog_post)

    with open(README_PATH, "w", encoding="utf-8") as file:
        file.write(updated)

    print(f"Updated README for {username}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise
