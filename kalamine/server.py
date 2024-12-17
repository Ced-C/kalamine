import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from importlib import metadata
from pathlib import Path
from xml.etree import ElementTree as ET
import json

import click
from livereload import Server  # type: ignore

from .generators import ahk, keylayout, klc, web, xkb
from .layout import KeyboardLayout, load_layout
from .www.index import get_page as get_main_page
from .corpus import get_corpuses, get_corpus


def keyboard_server(file_path: Path, angle_mod: bool = False) -> None:
    kb_layout = KeyboardLayout(load_layout(file_path), angle_mod)

    host_name = "localhost"
    webserver_port = 1664
    lr_server_port = 5500

    def main_page(layout: KeyboardLayout, angle_mod: bool = False) -> str:
        layout_ref = layout.meta["name"]
        if "url" in layout.meta:
            layout_ref = (
                f"""<a href="{layout.meta['url']}">{layout.meta['name']} 🔗</a>"""
            )

        return get_main_page(
            host_name,
            lr_server_port,
            angle_mod,
            layout,
            layout_ref,
            list(get_corpuses().keys()),
            str(metadata.version('kalamine'))
        )

    class LayoutHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs) -> None:  # type: ignore
            kwargs["directory"] = str(Path(__file__).parent / "www")
            super().__init__(*args, **kwargs)

        def do_GET(self) -> None:
            self.send_response(200)

            def send(
                page: str, content: str = "text/plain", charset: str = "utf-8"
            ) -> None:
                self.send_header("Content-type", f"{content}; charset={charset}")
                # no cash as one is likely working live on it
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(bytes(page, charset))
                # self.wfile.write(page.encode(charset))

            # XXX always reloads the layout on the root page, never in sub pages
            nonlocal kb_layout
            nonlocal angle_mod
            if self.path == "/favicon.ico":
                pass
            elif self.path == "/json":
                send(web.pretty_json(kb_layout), content="application/json")
            elif self.path == "/keylayout":
                # send(keylayout.keylayout(kb_layout), content='application/xml')
                send(keylayout.keylayout(kb_layout))
            elif self.path == "/ahk":
                send(ahk.ahk(kb_layout))
            elif self.path == "/klc":
                send(klc.klc(kb_layout), charset="utf-16-le", content="text")
            elif self.path == "/rc":
                send(klc.klc_rc(kb_layout), content="text")
            elif self.path == "/c":
                send(klc.klc_c(kb_layout), content="text")
            elif self.path == "/xkb_keymap":
                send(xkb.xkb_keymap(kb_layout))
            elif self.path == "/xkb_symbols":
                send(xkb.xkb_symbols(kb_layout))
            elif self.path == "/svg":
                utf8 = ET.tostring(web.svg(kb_layout).getroot(), encoding="unicode")
                send(utf8, content="image/svg+xml")
            elif self.path.split("/")[1] == "getcorpus": # looking for url like `/getcorpus/corpus`
                corpus_name = self.path.split("/")
                if len(corpus_name) < 3: #return error
                    pass
                else:
                    corpus_name = corpus_name[2]
                    _corpus = get_corpus(corpus_name)
                    if _corpus:
                        json_corpus = json.dumps(_corpus)
                        send(json_corpus, content="application/json")
                    else:
                        pass # is it good practice to send back an error ?
            elif self.path == "/":
                kb_layout = KeyboardLayout(load_layout(file_path), angle_mod)  # refresh
                send(main_page(kb_layout, angle_mod), content="text/html")
            else:
                return SimpleHTTPRequestHandler.do_GET(self)


    webserver = HTTPServer((host_name, webserver_port), LayoutHandler)
    thread = threading.Thread(None, webserver.serve_forever)

    try:
        thread.start()
        url = f"http://{host_name}:{webserver_port}/#/{kb_layout.meta['variant']}/ol60/en+fr"
        print(f"Server started: {url}")
        print("Hit Ctrl-C to stop.")
        webbrowser.open(url)

        # livereload
        lr_server = Server()
        lr_server.watch(str(file_path))
        lr_server.serve(host=host_name, port=lr_server_port)

    except KeyboardInterrupt:
        pass

    webserver.shutdown()
    webserver.server_close()
    thread.join()
    click.echo("Server stopped.")
