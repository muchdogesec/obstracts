## markdown helper
import textwrap
from urllib.parse import urljoin
import mistune, hyperlink
from mistune.renderers.markdown import MarkdownRenderer
from mistune.util import unescape


class MarkdownImageReplacer(MarkdownRenderer):
    def __init__(self, absolue_url, images):
        self.absolute_url = absolue_url
        self.images = images
        super().__init__()

    def image(self, token: dict[str, dict], state: mistune.BlockState) -> str:
        src = token["attrs"]["url"]
        if not hyperlink.parse(src).absolute:
            try:
                token["attrs"]["url"] = urljoin(self.absolute_url, self.images[src])
            except Exception as e:
                pass
        return super().image(token, state)

    def codespan(self, token: dict[str, dict], state: mistune.BlockState) -> str:
        token["raw"] = unescape(token["raw"])
        return super().codespan(token, state)

    @classmethod
    def get_markdown(cls, url, md_text, images):
        modify_links = mistune.create_markdown(escape=False, renderer=cls(url, images))
        return modify_links(md_text)
