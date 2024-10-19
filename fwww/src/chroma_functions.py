import chromadb

def getclient(host="localhost", port="8000"):
  chromaclient = chromadb.HttpClient(host, port)
  return chromaclient

def getcollection(chromaclient, dbname="defaultdb", initialize=False):
  print(f"  cf:opening {dbname}...")
  if initialize:
      if any(dbname == collection.name for collection in chromaclient.list_collections()):
        print(f"  cf:found duplicate collection {dbname}. Removing...")
        chromaclient.delete_collection(dbname)
  collection = chromaclient.get_or_create_collection(dbname, metadata={"hnsw:space": "cosine"}  )
  return(collection)

