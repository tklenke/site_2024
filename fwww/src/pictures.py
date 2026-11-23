# ABOUTME: Reads the gallery index, which names the pictures of each Google Groups thread.
# ABOUTME: Read once, at first use; with no index the site shows no pictures and works as without them.

import json
from urllib.parse import quote
from src.site_functions import url_from_source

# a picture links only to its attachment at Google Groups
PICTURE_LINK_START = 'https://groups.google.com/'

class PictureIndex:
    def __init__(self, strPath):
        """
        :param strPath: Path of the gallery index; empty when it is not set.
        """
        self.strPath = strPath
        self.dctThreads = None

    def threads(self):
        """
        The gallery index: for each thread id, its metadata and its pictures.

        :return: The index, or an empty dict when it is not set or cannot be read.
        """
        if self.dctThreads is None:
            self.dctThreads = self.read()
        return self.dctThreads

    def read(self):
        if not self.strPath:
            print("No pictures: the gallery index is not set (INDEX in [PICTURES])")
            return {}
        try:
            with open(self.strPath, 'r', encoding='utf-8') as f:
                dctThreads = json.load(f)
            if not isinstance(dctThreads, dict):
                raise ValueError("The content is not a JSON object")
            return dctThreads
        except (OSError, ValueError) as e:
            print(f"No pictures: cannot read the gallery index {self.strPath}: {e!r}")
            return {}

def get_threads(lstDocs, dctIndex, strThumbsUrl, setShown):
    """The threads of the documents that have pictures, each once, leaving out those in setShown."""
    lstThreads = []
    for dctDoc in lstDocs:
        strSource = dctDoc['source']
        if strSource in setShown or strSource not in dctIndex:
            continue
        setShown.add(strSource)
        dctEntry = dctIndex[strSource]
        lstThreads.append({
            'subject': dctEntry['metadata'].get('subject', ''),
            'date': dctEntry['metadata'].get('date', ''),
            'url': url_from_source(strSource)[0],
            'pictures': [{'thumbnail_url': strThumbsUrl + '/' + quote(dctImage['thumbnail_filename'], safe=''),
                          'url': dctImage['url'] if dctImage['url'].startswith(PICTURE_LINK_START) else None}
                         for dctImage in dctEntry['images']],
        })
    return lstThreads

def get_pictures(lstProvidedDocs, lstRelatedDocs, dctIndex, strThumbsUrl):
    """
    The threads with pictures among the documents of a job.

    A document names its thread, so the pictures are those of the whole thread. A document
    of another kind, or of a thread without pictures, has none.

    :param lstProvidedDocs: The documents the answer was given, in order.
    :param lstRelatedDocs: The other documents found, in order.
    :param dctIndex: The gallery index.
    :param strThumbsUrl: The address the thumbnails are served under.
    :return: (threads of the provided documents, threads of the related documents not
              among the provided ones); each thread with its subject, date, link and pictures.
    """
    setShown = set()
    lstProvided = get_threads(lstProvidedDocs, dctIndex, strThumbsUrl, setShown)
    return lstProvided, get_threads(lstRelatedDocs, dctIndex, strThumbsUrl, setShown)

def count_pictures(lstThreads):
    return sum(len(dctThread['pictures']) for dctThread in lstThreads)

def first_pictures(lstThreads, intMax):
    """The threads holding the first intMax pictures, in order; the last thread may be cut."""
    lstFirst = []
    intLeft = intMax
    for dctThread in lstThreads:
        if intLeft <= 0:
            break
        lstFirst.append({**dctThread, 'pictures': dctThread['pictures'][:intLeft]})
        intLeft -= len(lstFirst[-1]['pictures'])
    return lstFirst
