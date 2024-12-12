#!/usr/bin/env python3
"""Turns txt file to ngrams"""

import json
from os import listdir, path
from sys import argv

NGRAM_MAX_LENGTH = 5  # Quadrigrams
IGNORED_CHARS = "1234567890 \t\r\n\ufeff↵"


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

    return ngrams


def read_corpus(file_path: str, name: str = "", encoding="utf-8"):
    try:
        with open(file_path, "r", encoding=encoding) as file:
            corpus_txt = "↵".join(file.readlines())
        return {
            "name": name,
            #   "text": corpus_txt,
            "freq": parse_corpus(corpus_txt),
        }
    except:
        print("file could not be read")


def add_corpus():
    pass


def rm_corpus():
    # todo
    pass


if __name__ == "__main__":
    corpus = read_corpus(
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
