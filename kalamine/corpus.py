"""Turns txt file to ngrams"""

import json
from pathlib import Path
import appdirs
import click

NGRAM_MAX_LENGTH = 5  # Quadrigrams
IGNORED_CHARS = "1234567890 \t\r\n\ufeff↵"
APP_NAME = "Kalamine"
APP_AUTHOR = "1dk"


def parse_corpus(txt: str) -> dict:
    """Count ngrams in a text file.
    retuns a dict of ngrams
        ngrams[1]=symbols
        ngrams[2]=bigrames
        ngrams[3]=trigrams
        etc., up to NGRAM_COUNT
    ngrams[2] is shaped as { "aa": count }
    """

    ngrams = {}
    ngrams_count = {}  # ngrams_count counts the total number of ngrams[i] in corpus.

    txt = txt.lower()  # we want to be case **in**sensitive

    for ngram in range(1, NGRAM_MAX_LENGTH):
        ngrams[ngram] = {}
        ngrams_count[ngram] = 0

    def get_ngram(txt: str, ngram_start: int, ngram_length: int) -> str:
        """get a ngram of a given length at given position in txt
        returns empty string if ngram cannot be provided"""
        if txt[ngram_start] in IGNORED_CHARS:
            return ""
        if ngram_length <= 0:
            return ""
        if ngram_start + ngram_length >= len(txt):
            return ""

        ngram = txt[ngram_start : ngram_start + ngram_length]

        for n in ngram[1:]:  # 1st char already tested
            if n in IGNORED_CHARS:
                return ""

        return ngram

    for ngram_start in range(len(txt)):
        for ngram_length in range(NGRAM_MAX_LENGTH):
            _ngram = get_ngram(txt, ngram_start, ngram_length)

            if _ngram == "":
                continue

            if _ngram not in ngrams[ngram_length]:
                ngrams[ngram_length][_ngram] = 0

            ngrams[ngram_length][_ngram] += 1
            ngrams_count[ngram_length] += 1

    # sort the dictionary by symbol frequency (requires CPython 3.6+)
    def sort_by_frequency(table: dict, char_count: int, precision: int = 3) -> dict:
        sorted_dict = {}
        for key, count in sorted(table.items(), key=lambda x: -x[1]):
            freq = round(100 * count / char_count, precision)
            if freq > 0:
                sorted_dict[key] = freq
        return sorted_dict

    for ngram in range(1, NGRAM_MAX_LENGTH):
        ngrams[ngram] = sort_by_frequency(ngrams[ngram], ngrams_count[ngram], 4)

    return ngrams, ngrams_count


def read_corpus(file_path: str, name: str = "", encoding="utf-8") -> dict:
    try:
        path = Path(file_path)
        if not path.is_file:
            raise Exception("Error, this is not a file")
        if name == "":
            name = path.stem
        with path.open("r", encoding=encoding) as file:
            corpus_txt = "↵".join(file.readlines())
        ngrams_freq, ngrams_count = parse_corpus(corpus_txt)
        return {
            "name": name,
            #   "text": corpus_txt,
            "freq": ngrams_freq,
            "count": ngrams_count,
        }
    except:
        print("file could not be read")


def add_corpus(file_path: str, name: str = "", encoding="utf-8"):
    corpus = read_corpus(file_path, name, encoding)
    data_path = Path(appdirs.user_config_dir(APP_NAME, APP_AUTHOR)) / "corpuses"
    data_path.mkdir(parents=True, exist_ok=True)
    data_path = data_path / f"{name}.json"
    try:
        with data_path.open("w", encoding="utf-8") as outfile:
            json.dump(corpus, outfile, indent=4, ensure_ascii=False)
    except:
        print(f"Error: could not write to {data_path}")


def rm_corpus(name: str):
    corpus_path = Path(appdirs.user_config_dir(APP_NAME, APP_AUTHOR)) / "corpuses"
    corpus_path = corpus_path / f"{name}.json"
    try:
        corpus_path.unlink()
    except FileNotFoundError:
        print("Corpus do not exist")

def merge_corpuses(corpus_list:list, name:str)-> None:
    merge_corpus = {
        "name" : name,
        "freq" : {
            1:{},
            2:{},
            3:{},
        },
        "count": {},
    }
    ngram_length = -1
    for corpus_path in corpus_list:
        try:
            corpus = json.loads(corpus_path)
        except:
            click.echo(f"Warning: cannot open corpus called {corpus_path.stem} ; skipping this file")
            continue
        
        # merge on fewest ngram available, ignore above ngrams
        if ngram_length < 0:
            ngram_length = len(corpus["freq"].keys()+1)
        else:
            ngram_length = min( ngram_length, len(corpus["freq"].keys()+1))

        for n in range(ngram_length):
            for ngram, ngram_freq in corpus["freq"][n].items():
                if ngram not in merge_corpus:
                    merge_corpus["freq"][n][ngram] = ngram_freq
                else:
                    merge_corpus["freq"][n][ngram] = (
                        merge_corpus["freq"][n][ngram]*merge_corpus["count"][n] +
                        ngram_freq * corpus["count"][n]) / (merge_corpus["count"][n]+corpus["count"][n]) 

                merge_corpus["count"] += corpus["count"][ngram]

def get_corpus(name:str) -> str:
    """If corupus exist, provides its json, else, send empty str"""
    corpus_path = Path(appdirs.user_config_dir(APP_NAME, APP_AUTHOR)) / "corpuses" / f"{name}.json"
    if corpus_path.exists():
        with open(corpus_path, "r") as corpus:
            return json.load(corpus)
    return ""

def get_corpuses()-> dict:
    pass #todo
    """get all corpus in user data and std ones for web server"""
    corpuses = {}
    
    # misses : load std corpus 
    corpus_path = Path(appdirs.user_config_dir(APP_NAME, APP_AUTHOR)) / "corpuses"
    for file in corpus_path.glob("*.json"):
        if file.is_file():
            corpus_name = file.stem
            corpuses[corpus_name] = get_corpus(corpus_name)
    
    return corpuses 


if __name__ == "__main__":
    """corpus = read_corpus(
        "/home/cedc/Documents/Projets_perso/FOSS/kalamine/kalamine/www/corpus/hugo_fantine.txt",
        name="hugo_cc",
    )
    # for compatibility with current format
    results = {}
    results["name"] = corpus["name"]
    results["symbols"] = corpus["freq"][1]
    results["digrams"] = corpus["freq"][2]
    results["trigrams"] = corpus["freq"][3]

    print(corpus["freq"])
    count = {}
    for n in range(1, NGRAM_MAX_LENGTH):
        count[n] = sum(corpus["freq"][n].values())

    print(count)
    """
    add_corpus(
        "/home/cedc/Documents/Projets_perso/FOSS/kalamine/kalamine/www/corpus/hugo_fantine.txt",
        "test2",
    )
    rm_corpus("test")
