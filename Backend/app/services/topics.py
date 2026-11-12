import math
import re
from collections import Counter

MIN_REPOSITORIES_PER_TOPIC = 3
POWER_ITERATIONS = 30
REFINE_ITERATIONS = 10
TOPIC_TERMS = 2
TOPIC_WEIGHT = 2
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "its", "of", "on",
    "or", "that", "the", "this", "to", "using", "via", "with", "without", "your", "you", "we", "our", "all",
    "based", "simple", "small", "tiny", "fast", "lightweight", "easy", "new", "my", "other", "more", "some",
    "project", "repository", "repo", "source", "code", "implementation", "official", "written", "made", "use",
    "used", "app", "github", "io", "www", "http", "https", "com", "org", "v1", "v2", "v3",
    "python", "py", "javascript", "js", "typescript", "ts", "java", "kotlin", "go", "golang", "rust", "rs",
    "ruby", "rb", "php", "c", "cpp", "csharp", "cs", "swift", "scala", "haskell", "elixir", "lua", "perl",
    "shell", "bash", "dart", "julia", "zig", "nim", "ocaml", "clojure", "erlang", "lang",
}
WORD = re.compile(r"[a-zа-яё0-9]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def words(text: str) -> list[str]:
    found = WORD.findall(CAMEL_BOUNDARY.sub(" ", text.replace("-", " ").replace("_", " ")).casefold())
    return [word for word in found if len(word) > 1 and not word.isdigit() and word not in STOP_WORDS]


def stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def repository_texts(repo: dict) -> list[tuple[str, int]]:
    name = repo["full_name"].split("/", 1)[1]
    topics = [(topic, TOPIC_WEIGHT) for topic in repo.get("topics") or []]
    return [(name, 1), (repo.get("description") or "", 1), *topics]


def repository_terms(repo: dict) -> Counter:
    terms: Counter = Counter()
    for text, weight in repository_texts(repo):
        for word in words(text):
            terms[stem(word)] += weight
    for word in words(repo["full_name"].split("/", 1)[0]):
        del terms[stem(word)]
    return terms


def surface_forms(repositories: list[dict]) -> dict[str, str]:
    forms: Counter = Counter()
    for repo in repositories:
        for text, weight in repository_texts(repo):
            for word in words(text):
                forms[stem(word), word] += weight
    best: dict[str, str] = {}
    for (term, word), _ in sorted(forms.items(), key=lambda item: (-item[1], item[0][1])):
        best.setdefault(term, word)
    return best


def tfidf_vectors(documents: list[Counter]) -> list[dict[str, float]]:
    frequency = Counter(term for document in documents for term in document)
    count = len(documents)
    vectors = []
    for document in documents:
        vector = {
            term: (1 + math.log(times)) * (math.log((1 + count) / (1 + frequency[term])) + 1)
            for term, times in document.items()
            if frequency[term] > 1
        }
        vectors.append(normalized(vector))
    return vectors


def normalized(vector: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(value * value for value in vector.values()))
    return {term: value / norm for term, value in vector.items()} if norm else {}


def similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(term, 0.0) for term, value in left.items())


def sum_vectors(vectors: list[dict[str, float]]) -> dict[str, float]:
    total: Counter = Counter()
    for vector in vectors:
        total.update(vector)
    return dict(total)


def centroid(vectors: list[dict[str, float]]) -> dict[str, float]:
    return normalized(sum_vectors(vectors))


def principal_split(vectors: list[dict[str, float]]) -> list[int]:
    mean = {term: value / len(vectors) for term, value in sum_vectors(vectors).items()}
    direction = normalized({term: value - mean.get(term, 0.0) for term, value in max(vectors, key=len).items()})
    projections = [0.0] * len(vectors)
    for _ in range(POWER_ITERATIONS):
        shift = similarity(mean, direction)
        projections = [similarity(vector, direction) - shift for vector in vectors]
        weighted: Counter = Counter()
        for vector, projection in zip(vectors, projections):
            weighted.update({term: value * projection for term, value in vector.items()})
        total = sum(projections)
        direction = normalized({
            term: weighted.get(term, 0.0) - total * mean.get(term, 0.0) for term in set(weighted) | set(mean)
        }) or direction
    return [int(projection > 0) for projection in projections]


def refine(vectors: list[dict[str, float]], labels: list[int]) -> list[int]:
    for _ in range(REFINE_ITERATIONS):
        centers = [centroid([vector for vector, label in zip(vectors, labels) if label == side]) for side in (0, 1)]
        if not all(centers):
            return labels
        updated = [int(similarity(vector, centers[1]) > similarity(vector, centers[0])) for vector in vectors]
        if updated == labels:
            break
        labels = updated
    return labels


def bisect(vectors: list[dict[str, float]], count: int) -> list[int]:
    clusters = [list(range(len(vectors)))]
    while len(clusters) < count:
        largest = max(range(len(clusters)), key=lambda index: (len(clusters[index]), -index))
        members = clusters[largest]
        if len(members) < 2:
            break
        sides = refine([vectors[index] for index in members], principal_split([vectors[index] for index in members]))
        halves = [[index for index, side in zip(members, sides) if side == value] for value in (0, 1)]
        if not all(halves):
            break
        clusters[largest:largest + 1] = halves
    labels = [0] * len(vectors)
    for label, members in enumerate(clusters):
        for index in members:
            labels[index] = label
    return labels


def topic_count(repositories: int, limit: int) -> int:
    return max(1, min(limit, math.ceil(math.sqrt(repositories)), repositories // MIN_REPOSITORIES_PER_TOPIC))


def topic_name(vectors: list[dict[str, float]], forms: dict[str, str], taken: set[str]) -> str:
    weights: Counter = Counter()
    coverage: Counter = Counter()
    for vector in vectors:
        weights.update(vector)
        coverage.update(vector.keys())
    shared = [term for term in weights if coverage[term] > 1 or len(vectors) == 1]
    ranked = sorted(shared, key=lambda term: (-weights[term] * coverage[term], term))
    for size in range(TOPIC_TERMS, 0, -1):
        name = " · ".join(forms.get(term, term) for term in ranked[:size])
        if name and name not in taken:
            return name
    return ""


def cluster_repositories(repositories: list[dict], limit: int, fallback: str) -> tuple[list[int], list[str]]:
    vectors = tfidf_vectors([repository_terms(repo) for repo in repositories])
    forms = surface_forms(repositories)
    described = [index for index, vector in enumerate(vectors) if vector]
    count = topic_count(len(described), limit)
    if count < 2:
        return [0] * len(repositories), [topic_name([vectors[index] for index in described], forms, set()) or fallback]

    labels = [-1] * len(repositories)
    for index, label in zip(described, bisect([vectors[index] for index in described], count)):
        labels[index] = label
    adopt_undescribed(repositories, labels)

    clusters = sorted(set(labels), key=lambda label: (-labels.count(label), label))
    remap = {label: position for position, label in enumerate(clusters)}
    labels = [remap[label] for label in labels]
    names: list[str] = []
    for cluster in range(len(clusters)):
        members = [vectors[index] for index, label in enumerate(labels) if label == cluster and vectors[index]]
        names.append(topic_name(members, forms, set(names)) or f"{fallback} {cluster + 1}")
    return labels, names


def adopt_undescribed(repositories: list[dict], labels: list[int]) -> None:
    by_language: dict[str | None, Counter] = {}
    for repo, label in zip(repositories, labels):
        if label >= 0:
            by_language.setdefault(repo.get("language"), Counter())[label] += 1
    overall = Counter(label for label in labels if label >= 0)
    for index, repo in enumerate(repositories):
        if labels[index] < 0:
            votes = by_language.get(repo.get("language")) or overall
            labels[index] = min(votes, key=lambda label: (-votes[label], label))
