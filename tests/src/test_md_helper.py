from obstracts.server.md_helper import MarkdownImageReplacer


def test_replaces_images():
    assert (
        MarkdownImageReplacer.get_markdown("", "![](image.jpg)", {}).strip()
        == "![](image.jpg)"
    )
    assert (
        MarkdownImageReplacer.get_markdown(
            "", "![](image.jpg)", {"image.jpg": "https://example.com/example.image.jpg"}
        ).strip()
        == "![](https://example.com/example.image.jpg)"
    )
    assert (
        MarkdownImageReplacer.get_markdown(
            "https://someserver.net/service/",
            "![](image.jpg)",
            {"image.jpg": "https://example.com/example.image.jpg"},
        ).strip()
        == "![](https://example.com/example.image.jpg)"
    )
    assert (
        MarkdownImageReplacer.get_markdown(
            "https://someserver.net/service/",
            "![](image.jpg)",
            {"image.jpg": "/example.image.jpg"},
        ).strip()
        == "![](https://someserver.net/example.image.jpg)"
    )
    assert (
        MarkdownImageReplacer.get_markdown(
            "https://someserver.net/service/",
            "![](image.jpg)",
            {"image.jpg": "example.image.jpg"},
        ).strip()
        == "![](https://someserver.net/service/example.image.jpg)"
    )
