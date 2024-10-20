import fcntl, os, time, errno

def get_flags_from_mode(mode):
    if mode == 'r':
        return os.O_RDONLY
    elif mode == 'w':
        return os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    elif mode == 'a':
        return os.O_WRONLY | os.O_CREAT | os.O_APPEND
    else:
        raise ValueError(f"Unsupported mode: {mode}")

def open_with_lock(path, mode='r', flags=os.O_CREAT | os.O_EXCL, max_retries=50, wait_secs=0.1):
    """
    Opens a file with a lock, ensuring fault tolerance and preventing concurrent access.
    Uses shared lock for reading and exclusive lock for writing/appending.

    Args:
        path: The path to the file.
        mode: The mode in which to open the file (e.g., 'r', 'w', 'a').
        flags: Additional flags for opening the file (e.g., os.O_CREAT, os.O_EXCL).
        max_retries: Maximum number of retries to acquire the lock.
        wait_secs: Time to wait between retries.

    Returns:
        A file object for the opened file.

    Raises:
        OSError: If the file cannot be opened or locked after multiple retries.
    """
    retries = 0

     # Only apply os.O_CREAT | os.O_EXCL for writing or appending modes
    file_flags = get_flags_from_mode(mode)
    if 'w' in mode or 'a' in mode:
        file_flags |= os.O_CREAT | os.O_EXCL

    while retries < max_retries:
        try:
            # Open the file with the appropriate flags
            fd = os.open(path, file_flags)
        except OSError as e:
            if e.errno == errno.EEXIST and ('w' in mode or 'a' in mode):
                # File exists, try to open it without O_EXCL flag for write or append
                fd = os.open(path, get_flags_from_mode(mode))
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as e:
                    if e.errno == errno.EWOULDBLOCK:
                        print(f"File {path} is currently locked. Retrying {retries+1}/{max_retries}...")
                        time.sleep(wait_secs)
                        retries += 1
                        continue
                    else:
                        print(f"open_with_lock 1 exception {e}")
                        raise
            else:
                print(f"open_with_lock 2 exception {e}")
                raise

        # Apply the appropriate lock: shared for reading, exclusive for writing/appending
        try:
            if 'r' in mode:
                # Shared lock for reading
                fcntl.flock(fd, fcntl.LOCK_SH)
            else:
                # Exclusive lock for writing or appending
                fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as e:
            if e.errno == errno.EWOULDBLOCK:
                print(f"File {path} is locked by another process. Retrying {retries+1}/{max_retries}...")
                time.sleep(wait_secs)
                retries += 1
                continue
            else:
                print(f"open_with_lock 3 exception {e}")
                raise

        # Return a file object instead of just the file descriptor
        return os.fdopen(fd, mode)

    # If we've reached the maximum retries, raise an error
    raise OSError(f"Could not acquire lock for {path} after {max_retries} retries")






if __name__ == '__main__':
    import threading
    MAX_RETRIES = 2
    WAIT_SECS = .5
    test_file = 'test_lock_file.txt'

    def write_with_lock(file_path, hold_time):
        try:
            print("Thread 1: Attempting to open file for writing and acquire lock...")
            fd = open_with_lock(file_path, mode='w')
            print("Thread 1: File locked for writing.")
            fd.write("Thread 1: Writing to file...\n")
            time.sleep(hold_time)  # Hold the lock for some time
            fd.close()
            print("Thread 1: Write lock released.")
        except OSError as e:
            print(f"Thread 1: Error during write: {e}")

    def append_with_lock(file_path):
        try:
            print("Thread 2: Attempting to open file for appending and acquire lock...")
            fd = open_with_lock(file_path, mode='a')
            print("Thread 2: File locked for appending.")
            fd.write("Thread 2: Appending to file...\n")
            fd.close()
            print("Thread 2: Append lock released.")
        except OSError as e:
            print(f"Thread 2: Error during append: {e}")

    def read_with_lock(file_path):
        try:
            print("Thread 3: Attempting to open file for reading...")
            fd = open_with_lock(file_path, mode='r')
            print("Thread 3: File opened for reading.")
            content = fd.read(1024)
            print(f"Thread 3: Read content: {content}")
            fd.close()
            print("Thread 3: Read operation completed.")
        except OSError as e:
            print(f"Thread 3: Error during read: {e}")


    # Thread 1 will acquire a write lock and hold it for a while
    t1 = threading.Thread(target=write_with_lock, args=(test_file, 5))
    
    # Thread 2 will try to acquire an append lock (it should wait until Thread 1 is done)
    t2 = threading.Thread(target=append_with_lock, args=(test_file,))
    
    # Thread 3 will try to read the file (it can run concurrently with the other operations)
    t3 = threading.Thread(target=read_with_lock, args=(test_file,))

    # Start the threads
    t1.start()
    time.sleep(1)  # Ensure thread 1 starts and locks the file first
    t2.start()
    time.sleep(1)  # Start thread 3 after thread 2 has been blocked by thread 1
    t3.start()

    # Wait for all threads to finish
    t1.join()
    t2.join()
    t3.join()
