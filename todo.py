import argparse
import cmd
import datetime
import re
import shlex
import sys
from datetime import timedelta

import yaml
from dateutil.parser import parse as date_parse
from dateutil.relativedelta import relativedelta
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive


# Utility function to read the configuration from a YAML file
def get_config():
    with open("settings.yaml", 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)


class Task:
    """
    The Task class represents a task with its various attributes including
    its state, name, priority, initialization date, and due date.
    """

    # Define constants for task states
    STATE_TODO = 'TODO'
    STATE_DONE = 'DONE'

    # Define a date format constant for string-date conversions
    DATE_FORMAT = '%Y-%m-%d'

    def __init__(self, id, name, priority, init_date, due_date=None, state=STATE_TODO):
        """
        Initialize a new Task object with the provided attributes.
        """
        self.id = int(id)  # The task ID
        self.name = name  # The task name
        self.priority = priority  # The task priority
        self.init_date = init_date  # The task initialization date
        self.due_date = due_date  # The task due date (optional)
        self.state = state  # The task state (default is 'TODO')

    @classmethod
    def from_string(cls, line):
        """
        A class method that constructs a Task object from a string.
        """
        # Split the string into components
        parts = line.strip().split(" ", 5)
        id, priority, init_date, due_date_str, state, name = parts

        # Convert string dates to datetime objects
        init_date = datetime.datetime.strptime(init_date, cls.DATE_FORMAT)
        due_date = datetime.datetime.strptime(due_date_str, cls.DATE_FORMAT) if due_date_str != 'None' else None

        # Convert priority to integer
        priority = int(priority)

        # Return a new Task object created from the parsed string components
        return cls(int(id), name, priority, init_date, due_date, state)

    def to_string(self):
        """
        Converts a Task object into a string format.
        """
        # If due date is present, convert it to string; if not, use 'None'
        due_date_str = self.due_date.strftime(self.DATE_FORMAT) if self.due_date else 'None'

        # Return the string representation of the Task object
        return f'{self.id} {self.priority} {self.init_date.strftime(self.DATE_FORMAT)} {due_date_str} {self.state} {self.name}'


class TodoList:
    """
    The TodoList class represents a todo list saved in a Google Drive file.
    It provides methods for reading and writing tasks to the file, and for
    various task operations like adding, marking as done, listing, etc.
    """

    def __init__(self, file_id):
        """
        Initialize a new TodoList object. Authenticate with Google Drive,
        read tasks from the file with the given ID, and store them in memory.
        """
        gauth = GoogleAuth(settings_file="settings.yaml")  # Auth with Google Drive
        gauth.LocalWebserverAuth()  # Creates local webserver and auto handles authentication.
        self.drive = GoogleDrive(gauth)  # Get access to Google Drive
        self.file_id = file_id  # Store the ID of the file where the tasks are stored
        self.tasks = self.read_tasks()  # Read tasks from the file into memory

    def read_tasks(self):
        """
        Read tasks from the Google Drive file and return them as a list of Task objects.
        """
        # Create a file object with the given ID
        file = self.drive.CreateFile({'id': self.file_id})

        # If the file is a Google Docs document, export it; otherwise, download it
        if 'application/vnd.google-apps.document' in file['mimeType']:
            content = file.GetContentString(mimetype='text/plain')
        else:
            content = file.GetContentString()

        # Parse each line of the file content into a Task object and store them in a list
        tasks = []
        for line in content.splitlines():
            task = Task.from_string(line)
            tasks.append(task)
        return tasks

    def write_tasks(self):
        """
        Write tasks from memory back to the Google Drive file.
        """
        # Create a file object with the given ID
        file = self.drive.CreateFile({'id': self.file_id})

        # Convert each task to a string and join them with newline characters
        content = "\n".join(task.to_string() for task in self.tasks)

        # Write the task strings to the file and upload the file
        file.SetContentString(content)
        file.Upload()

    def calculate_due_date(self, due_date):
        """
        Calculate a due date based on a string description.
        """
        # If no due date is given, default to a week from now
        if due_date is None:
            return datetime.datetime.now() + datetime.timedelta(weeks=1)

        # If 'today' or 'tomorrow' is given, calculate the corresponding date
        if due_date == 'today':
            return datetime.datetime.now()
        if due_date == 'tomorrow':
            return datetime.datetime.now() + datetime.timedelta(days=1)

        # If a number of weeks or days is given, calculate the corresponding date
        if due_date.endswith('w'):
            weeks = int(due_date.rstrip('w'))
            return datetime.datetime.now() + datetime.timedelta(weeks=weeks)
        if due_date.endswith('d'):
            days = int(due_date.rstrip('d'))
            return datetime.datetime.now() + datetime.timedelta(days=days)

        # If a specific date is given, parse it
        return datetime.datetime.strptime(due_date, '%Y-%m-%d')

    def add_task(self, name, due_date=None, priority=5):
        """
        Add a task to the list and write the updated list to the file.
        """
        # Calculate the due date based on the provided description
        due_date = self.calculate_due_date(due_date)

        # Create a new task with the given attributes and an ID that's one greater than the current highest ID
        new_task = Task(id=len(self.tasks) + 1, name=name, priority=priority,
                        init_date=datetime.datetime.now(), due_date=due_date,
                        state=Task.STATE_TODO)

        # Append the new task to the list and write the updated list to the file
        self.tasks.append(new_task)
        self.write_tasks()

    def mark_task_done(self, task_id):
        """
        Mark a task as done and write the updated list to the file.
        """
        # Iterate over the tasks
        for task in self.tasks:
            # If a task with the given ID is found, mark it as done and update its due date
            if task.id == int(task_id):
                task.state = Task.STATE_DONE
                task.due_date = datetime.datetime.now()

                # Write the updated list to the file
                self.write_tasks()

                # Exit the method
                return

        # If no task with the given ID is found, print a message
        print(f"No task found with ID {task_id}")

    def list_tasks(self):
        """
        Print all tasks that are not done, sorted by priority (high to low).
        """
        # Filter the tasks to get only the ones that are not done
        tasks = sorted((t for t in self.tasks if t.state == Task.STATE_TODO),
                       key=lambda t: t.priority, reverse=True)

        # Print each task
        for task in tasks:
            print(task.to_string())

    def renumber_tasks(self):
        """
        Renumber tasks based on their current order and write the updated list to the file.
        """
        # Sort tasks by whether they're done and their initialization date, and then renumber them
        self.tasks.sort(key=lambda t: (t.state == Task.STATE_DONE, t.init_date))
        for i, task in enumerate(self.tasks, start=1):
            task.id = str(i)

        # Write the updated list to the file
        self.write_tasks()

    def top_tasks(self):
        """
        Print the top 5 tasks that are either high-priority or due today or earlier.
        """
        # Filter the tasks to get only the ones that are not done and either high-priority or due today or earlier
        tasks = sorted((t for t in self.tasks if t.state == Task.STATE_TODO and
                        (t.priority == 1 or (t.due_date and t.due_date.date() <= datetime.datetime.today().date()))),
                       key=lambda t: t.priority, reverse=True)

        # Print the first 5 tasks
        for task in tasks[:5]:
            print(task.to_string())

    def list_completed_today(self):
        """
        Print all tasks that were completed today.
        """
        # Filter the tasks to get only the ones that were completed today
        tasks = [t for t in self.tasks if
                 t.state == Task.STATE_DONE and t.due_date.date() == datetime.datetime.today().date()]

        # Print each task
        for task in tasks:
            print(task.to_string())

    def postpone_task(self, task_id, duration):
        """
        Postpone a task's due date by a certain duration and write the updated list to the file.
        """
        # Iterate over the tasks
        for task in self.tasks:
            # If a task with the given ID is found, postpone its due date
            if task.id == task_id:
                # If the duration is in weeks, postpone the due date by that number of weeks
                if duration[-1].lower() == 'w':
                    weeks = int(duration[:-1])
                    task.due_date += datetime.timedelta(weeks=weeks)
                # If the duration is in days, postpone the due date by that number of days
                elif duration[-1].lower() == 'd':
                    days = int(duration[:-1])
                    task.due_date += datetime.timedelta(days=days)

                # Write the updated list to the file
                self.write_tasks()

                # Exit the method
                return

        # If no task with the given ID is found, print a message
        print(f"No task found with ID {task_id}")

    def prune(self):
        """
        Removes all tasks marked as DONE and older than a month.
        """
        # Get the current time
        now = datetime.datetime.now()

        # Define a timedelta for one month ago
        one_month_ago = now - timedelta(days=30)

        # Create a new list with the tasks we want to keep
        self.tasks = [task for task in self.tasks
                      if not (task.state == "DONE" and task.due_date < one_month_ago)]

        # Inform the user that pruning is completed
        print('Pruned tasks.')


class TodoShell(cmd.Cmd):
    # Setting up the introductory message and prompt for the shell
    intro = 'Welcome to the todo shell. Type help or ? to list commands.\n'
    prompt = '(todo) '

    def __init__(self):
        """
        Initialization of the command line shell.
        """
        # Initializing the parent class
        super().__init__()

        # Create a TodoList instance using a specific Google Drive file ID

        # Get configuration from settings.yaml
        config = get_config()

        # Create a TodoList instance
        self.todo_list = TodoList(config['file_id'])

    def do_add(self, arg):
        """
        Command to add a new task.
        Format: add "TASK_NAME" [-d DUE_DATE] [-p PRIO]
        """
        # Parse the arguments
        task_name, due_date, priority = self.parse_args(arg)

        # Add a new task to the list
        self.todo_list.add_task(task_name, due_date, priority)

    def do_done(self, arg):
        """
        Command to set a task to done.
        Format: done <task id> [<task id>...]
        """
        # Iterate over the task IDs given as arguments and mark each one as done
        for task_id in arg.split():
            self.todo_list.mark_task_done(task_id)

    def do_ls(self, arg):
        """
        Command to list all TODO tasks.
        Format: ls
        """
        self.todo_list.list_tasks()

    def do_renumber(self, arg):
        """
        Command to renumber all tasks.
        Format: renumber
        """
        self.todo_list.renumber_tasks()

    def do_top(self, arg):
        """
        Command to list the top 5 TODO tasks.
        Format: top
        """
        self.todo_list.top_tasks()

    def do_completed(self, arg):
        """
        Command to list all tasks completed today.
        Format: completed
        """
        self.todo_list.list_completed_today()

    def do_postpone(self, arg):
        """
        Command to postpone a task.
        Format: postpone TASK_ID DURATION
        """
        # Split the argument into task ID and duration
        task_id, duration = arg.split()

        # Postpone the task
        self.todo_list.postpone_task(task_id, duration)

    def do_prune(self, arg):
        """
        Command to remove tasks in state DONE that are older than 1 month.
        Format: PRUNE
        """
        # Prune the tasks and write the updated list to the file
        self.todo_list.prune()
        self.todo_list.write_tasks()

    def do_quit(self, arg):
        """
        Command to exit the shell.
        Format: quit
        """
        print('Exiting...')
        return True

    # Define command aliases
    do_list = do_ls
    do_l = do_ls
    do_a = do_add
    do_d = do_done
    do_q = do_quit
    do_c = do_completed
    do_p = do_postpone
    do_r = do_renumber

    def parse_args(self, arg):
        """
        Parse the arguments given to the add command.
        """
        parser = argparse.ArgumentParser()

        # Add arguments for task name, due date, and priority
        parser.add_argument("name", nargs='+')
        parser.add_argument("-d", "--due_date",
                            help="Due date for the task. Format: 'today', 'tomorrow', '1w', or 'YYYY-MM-DD'. Default is '1w'",
                            default='1w')
        parser.add_argument("-p", "--priority", type=int, choices=range(1, 6),
                            help="Priority of the task. Must be an integer between 1 (highest) and 5 (lowest). Default is 5.",
                            default=5)

        # Parse the arguments and return the task name, due date, and priority
        args = parser.parse_args(shlex.split(arg))
        return ' '.join(args.name), args.due_date, args.priority

    def default(self, line):
        """
        Method called when a command entered is not recognized.
        """
        print(f'Command not recognized: {line}')

    def cmdloop(self, intro=None):
        """
        Method to start the cmdloop over and over again,
        catching KeyboardInterrupt and printing '^C' instead of quitting.
        """
        while True:
            try:
                super().cmdloop(intro="")
                break
            except KeyboardInterrupt:
                print('^C')


# The following block of code allows this python script to be both imported as a module
# and run as a standalone script
if __name__ == '__main__':

    # Check if there are command line arguments passed to the script
    if len(sys.argv) > 1:
        # Create a top-level parser object
        parser = argparse.ArgumentParser(description='Manage your todo list.')
        # Create subparsers for each command
        subparsers = parser.add_subparsers(dest='command')

        # Parser for 'add' command
        parser_a = subparsers.add_parser('add', help='add task')
        parser_a.add_argument('task_name', nargs='?', default='')
        parser_a.add_argument('-d', '--due_date')
        parser_a.add_argument('-p', '--priority', type=int, choices=range(1, 6), default=5)

        # Parser for 'done' command
        parser_d = subparsers.add_parser('done', help='mark task done')
        parser_d.add_argument('task_name', nargs='*', default=[])

        # Parser for 'completed' command
        parser_c = subparsers.add_parser('completed', help='list tasks completed today')

        # Parsers for other commands
        parser_l = subparsers.add_parser('ls', help='list tasks')
        parser_ren = subparsers.add_parser('renumber', help='renumber tasks')
        parser_top = subparsers.add_parser('top', help='list top tasks')

        # Parser for 'postpone' command
        parser_p = subparsers.add_parser('postpone', help='postpone task')
        parser_p.add_argument('task_id', help='ID of the task to postpone')
        parser_p.add_argument('duration', help='Duration to postpone (example: 1w for one week)')

        # Parse command line arguments
        args = parser.parse_args()

        # Get configuration from settings.yaml
        config = get_config()

        # Create a TodoList instance
        todo_list = TodoList(config['file_id'])

        # Call appropriate function based on the command
        if args.command == 'done':
            for task_id in args.task_name:  # iterate over each task ID
                todo_list.mark_task_done(task_id)
        elif args.command == 'add':
            # Parse the due date
            if args.due_date:
                if args.due_date.lower() == 'today':
                    due_date = datetime.datetime.today()
                elif args.due_date.lower() == 'tomorrow':
                    due_date = datetime.datetime.today() + datetime.timedelta(days=1)
                elif re.match(r'^\d+w$', args.due_date.lower()):
                    weeks = int(args.due_date[:-1])
                    due_date = datetime.datetime.today() + relativedelta(weeks=+weeks)
                else:
                    due_date = date_parse(args.due_date)
            else:
                due_date = None
            todo_list.add_task(args.task_name, due_date, args.priority)
        elif args.command == 'ls':
            todo_list.list_tasks()
        elif args.command == 'renumber':  # handle 'ren' command
            todo_list.renumber_tasks()
        elif args.command == 'top':  # handle 'top' command
            todo_list.top_tasks()
        if args.command == 'completed':  # handle 'c' command
            todo_list.list_completed_today()
        if args.command == 'postpone':
            todo_list.postpone_task(args.task_id, args.duration)
    else:
        # If no command line arguments are passed, start the command line shell
        TodoShell().cmdloop()
