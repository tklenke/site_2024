# ABOUTME: Reads the gallery index, which names the pictures of each Google Groups thread.
# ABOUTME: Read once, at first use; with no index the site shows no pictures and works as without them.

import json

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
