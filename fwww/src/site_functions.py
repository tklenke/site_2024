from markupsafe import Markup, escape
import threading, os, string, random, time, json

def sanitize(txt):
    # my santize functions for unknown text
    return Markup(txt)

def get_process_id(nChars):
    characters = string.ascii_letters + string.digits
    unique_key = ''.join(random.choice(characters) for _ in range(nChars))
    return(unique_key)

def new_question(input, directory, nIdLen):
    processId = get_process_id(nIdLen)
    jsonFilePath = os.path.join(directory, processId + ".json")
    input['status'] = 'new'
    input['created'] = time.time()
    # Save the dictionary to a JSON file
    with open(jsonFilePath, "w") as f:
        json.dump(input, f)
    return processId

def get_process_info(directory, processId=None, filename=None ):
    data = {}
    if not filename:
        file_path = os.path.join(directory, processId + ".json")
    else:
        file_path = os.path.join(directory, filename)
    try:
        with open(file_path, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON file: {filename} {e}")
                return data
    except IOError as e:
         print(f"Error processing JSON file: {filename} {e}")
         return data

#####
#  Write process dictionary to process file        
#####
def update_process_info(info, directory, processId=None, filename=None ):
    if not filename:
        file_path = os.path.join(directory, processId + ".json")
    else:
        file_path = os.path.join(directory, filename)
    info['update_time'] = time.time()
    try:
        # Save the dictionary to a JSON file
        with open(file_path, "w") as f:
            json.dump(info, f)

    except IOError as e:
        print(f"Error updateing JSON file: {e}")

#####
#  Write process status to process file and return json data as dictionary
#####
def update_process_status(status, directory, processId=None, filename=None ):
    data = {}
    if not filename:
        file_path = os.path.join(directory, processId + ".json")
    else:
        file_path = os.path.join(directory, filename)

    data = get_process_info(directory, processId, filename)

    data["status"] = status
    data[ status + "_time"] = time.time()

    update_process_info(data, directory, processId, filename )
    return data




