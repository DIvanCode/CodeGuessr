from app.services.topics import cluster_repositories, repository_terms, topic_count


def repo(name: str, description: str = "", topics: list[str] | None = None, language: str | None = None) -> dict:
    return {"full_name": f"acme-labs/{name}", "description": description, "topics": topics or [], "language": language}


def test_terms_skip_owner_stop_words_and_plurals() -> None:
    terms = repository_terms(repo("acme-parser", "A fast parser for Python templates", ["templates"]))
    assert "acme" not in terms and "python" not in terms and "fast" not in terms
    assert terms["template"] == 3
    assert terms["parser"] == 2


def test_topic_count_grows_with_repositories_up_to_limit() -> None:
    assert topic_count(5, 6) == 1
    assert topic_count(16, 6) == 4
    assert topic_count(300, 6) == 6


def test_small_owner_gets_single_topic() -> None:
    labels, names = cluster_repositories([repo("one"), repo("two")], 6, "Разное")
    assert labels == [0, 0]
    assert names == ["Разное"]


def test_repositories_are_clustered_by_shared_terms() -> None:
    repositories = [
        repo("weather-bot", topics=["telegram"]), repo("notes-bot", topics=["telegram"]),
        repo("music-bot", "Discord bot"), repo("snake", topics=["game"]),
        repo("tetris", "Terminal game"), repo("chess", topics=["game"]),
    ]
    labels, names = cluster_repositories(repositories, 6, "Разное")
    assert labels[:3] == [labels[0]] * 3
    assert labels[3:] == [labels[3]] * 3
    assert labels[0] != labels[3]
    assert sorted(names) == ["bot · telegram", "game"]
    assert cluster_repositories(repositories, 6, "Разное") == (labels, names)


def test_undescribed_repositories_follow_their_language() -> None:
    repositories = [
        repo("weather-bot", topics=["telegram"], language="Python"), repo("notes-bot", topics=["telegram"], language="Python"),
        repo("music-bot", "Discord bot", language="Python"), repo("snake", topics=["game"], language="Go"),
        repo("tetris", "Terminal game", language="Go"), repo("chess", topics=["game"], language="Go"),
        repo("misc", language="Go"),
    ]
    labels, _ = cluster_repositories(repositories, 6, "Разное")
    assert labels[-1] == labels[3]
