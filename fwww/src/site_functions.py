from markupsafe import Markup, escape
import threading, os, string, random, time, json, re
from src.open_with_lock import open_with_lock
from flask import Flask, render_template, request, url_for, flash, redirect, \
                  jsonify, session

def sanitize(txt):
    # my santize functions for unknown text
    return Markup(txt)

def dedupe_list_of_docs(data):
    deduped = {}

    for entry in data:
        key3 = entry["source"]
        
        # Check if key3 is already in the deduped dictionary
        if key3 not in deduped or entry["score"] > deduped[key3]["score"]:
            # Update deduped dictionary with entry having the highest key2 value for key3
            deduped[key3] = {"id": entry["id"], "score": entry["score"]}
    
    # Convert the deduped dictionary back to a list of dicts
    return [{"id": v["id"], "score": v["score"], "source": k} for k, v in deduped.items()]

def render_markdown_file(mdfilepath):
    # This could be cached for a more high traffic site
    # Read the Markdown file
    with open(mdfilepath, 'r') as f:
        markdown_text = f.read()
    # Render the HTML content in a template
    return render_template('markdown.html', md_content=markdown_text)

def extract_originid_from_source(filepath):
  #Returns: A tuple containing the extracted number and a code indicating the matched pattern:
  #    - 0: If no pattern matched.
  #    - 1: If the "aeroelectric/page" pattern matched.
  #    - 2: If the "news/news_" pattern matched.
  #    - 3: If the "msgs/" pattern matched.
    patterns = {
        1: r"/aeroelectric/page(?P<originid>\d+)",
        2: r"/news/news_(?P<originid>\d+)",
        3: r"/msgs/[A-Za-z0-9_\-]+/(?P<originid>[A-Za-z0-9_\-]+)\.txt"
    }
    for code, pattern in patterns.items():
        match = re.search(pattern, filepath)
        if match:
            return match.group("originid"), code
    return filepath, 0

def url_from_source(source):
    # ./data/news/news_78.txt
    # ./data/msgs/H/Hmt8MVDA4C4.md
    # ./data/aeroelectric/page42.txt
    base_urls = ["http://aeroelectric.com/Connection/R12%20Searchable%20Merged%20Chapters.pdf#page=", \
                 "http://cozybuilders.org/newsletters/news_", \
                 "https://groups.google.com/g/cozy_builders/c/"]
    
    originid, code = extract_originid_from_source(source)
    if code == 1:
        return (base_urls[code-1]+originid,f"AeroElectric Connection page {originid}")
    elif code == 2:
        if int(originid) < 76:
            return (base_urls[code-1]+originid+".html",f"Cozy Newsletters Number {originid}")
        else:
            return (base_urls[code-1]+originid+".pdf",f"Cozy Newsletters Number {originid}")
    elif code == 3:
        return (base_urls[code-1]+originid,f"Cozy Builders Google Group Message {originid}")
    #else code 0    
    return (" ",f"Source Document {source} Not Found")


def get_process_id(nChars):
    characters = string.ascii_letters + string.digits
    unique_key = ''.join(random.choice(characters) for _ in range(nChars))
    return(unique_key)

def get_job_path(directory, processId=None, filename=None):
    if not filename:
        file_path = os.path.join(directory, processId + ".json")
    else:
        file_path = os.path.join(directory, filename)
    return file_path

def new_question(input, directory, nIdLen):
    processId = get_process_id(nIdLen)
    jsonFilePath = os.path.join(directory, processId + ".json")
    input['process_id'] = processId
    input['status'] = 'new'
    input['created'] = time.time()
    # Save the dictionary to a JSON file
    with open_with_lock(jsonFilePath, "w") as f:
        json.dump(input, f)
    return processId

def get_process_info(directory, processId=None, filename=None ):
    data = {}
    job_path = get_job_path(directory, processId, filename)
    try:
        with open_with_lock(job_path, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON file: {filename} {e}")
                return data
    except IOError as e:
         print(f"Error processing JSON file: {filename} {e}")
         return data
    
def get_all_jobs_info(directory):
    aJobInfo = []
    for filename in os.listdir(directory):
        aJobInfo.append(get_process_info(directory,filename=filename))
    return sorted(aJobInfo, key=lambda x: x['created'], reverse=True)   

#####
#  Write process dictionary to process file        
#####
def update_process_info(info, directory, processId=None, filename=None ):
    job_path = get_job_path(directory, processId, filename)
    info['update_time'] = time.time()
    try:
        # Save the dictionary to a JSON file
        with open_with_lock(job_path, "w") as f:
            json.dump(info, f)

    except IOError as e:
        print(f"Error updateing JSON file: {e}")

#####
#  Write process status to process file and return json data as dictionary
#####
def update_process_status(status, directory, processId=None, filename=None ):
    data = {}
    data = get_process_info(directory, processId, filename)
    data["status"] = status
    data[ status + "_time"] = time.time()
    update_process_info(data, directory, processId, filename )
    return data




