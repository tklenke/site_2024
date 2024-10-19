import threading, os, time, json, queue
from src.site_functions import get_process_info, update_process_status, update_process_info

def process_question(question):
    time.sleep(5)
    return "Question Answer here"

# ---- FILE PROCESSING STUFF
class FileProcessorThread(threading.Thread):
    instance = None

    def __init__(self, job_path, job_queue):
        if FileProcessorThread.instance:
            raise RuntimeError("Thread already running")
        FileProcessorThread.instance = self
        threading.Thread.__init__(self)
        self.daemon = True
        self.job_path = job_path
        self.job_queue = job_queue
        super().__init__()
        self.start()  # Start the thread immediately

    def run(self):
        processedJobs = []
        while True:
            item = self.job_queue.get()
            print(f'Working on {item}')
            self.job_queue.task_done()
            for filename in os.listdir(self.job_path):
                if filename in processedJobs:
                    continue
                data = get_process_info(filename=filename,directory=self.job_path)
                if data['status'] != "new":
                    processedJobs.append(filename)
                    continue
                #set status to started
                data = update_process_status("start",filename=filename,directory=self.job_path)
                # Validate required keys and handle missing ones gracefully
                if "query" not in data or data.get("query") is None:
                    print(f"{filename}: Missing 'query' key or null value in JSON data.")
                    update_process_status("error",filename=filename, directory=self.job_path)
                    continue
                #run
                result = process_question(data['query'])
                data["result"] = result
                #set status to completed
                data['status'] = 'complete'
                data['complete_time'] = time.time()
                update_process_info(data, filename=filename, directory=self.job_path)
                processedJobs.append(filename)
