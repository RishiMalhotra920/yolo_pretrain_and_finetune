import subprocess

import color_code_error_messages  # noqa: F401
import torch
import yaml


def load_and_validate_yaml_file(path: str) -> dict:
    """
    Load and validate the yaml file
    """
    with open(path, "r") as file:
        queue = yaml.safe_load(file)

    for task in queue["tasks"]:
        if task.get("run") is None:
            raise ValueError("run key is required in the yaml task.")
        if task.get("git_checkout_target") is None:
            raise ValueError("branch or commit key is required in the yaml task.")
        if "rm" in task["run"]:
            raise ValueError("rm command is not allowed in the yaml task.")

    return queue


def reset_cuda() -> None:
    """
    Reset the cuda device
    """
    torch.cuda.empty_cache()
    # subprocess.run("nvidia-smi --gpu-reset", shell=True, text=True, check=True)


def start_train_queue(path: str) -> None:
    """
    Start the training queue. The training queue is a list of tasks that are executed sequentially.
    The tasks are stored in a yaml file called train_queue.yaml.
    tasks have an index which can be a float. tasks are not in order of index.

    The idea is that you can queue up training commands in the train_queue.yaml file and then run this script.
    If you want to reorder the queue, you can change the indexes of tasks in the yaml file.
    """
    print("Starting training queue...")
    task_index = 0
    num_tasks = float("inf")

    while task_index < num_tasks:
        queue = load_and_validate_yaml_file(path=path)

        task = queue["tasks"][task_index]

        if not task:
            print("No more tasks in the queue.")
            return

        print(
            f"\033[1;36m============================================== Executing task {task_index}: {task['name']} ==============================================\033[0m\n"
        )
        print(
            f"\033[1;36mCheckout to branch/commit {task['git_checkout_target']} and execute tasks:\n{task['run']}\033[0m\n\n"
        )

        try:
            subprocess.run(
                f"git checkout {task['git_checkout_target']} && git pull",
                shell=True,
                text=True,
                check=True,
            )

            # reset cuda cache in between training runs
            reset_cuda()

            subprocess.run(task["run"], shell=True, text=True, check=True)

            print(
                f"\033[1;32mTask {task_index}: {task['name']} executed successfully\033[0m\n"
            )
        except subprocess.CalledProcessError as e:
            print(
                f"\033[1;31mTask {task_index}: {task['name']} failed with error: {e}\033[0m\n"
            )

        task_index += 1
        num_tasks = len(queue["tasks"])

    print("All tasks executed successfully.")


if __name__ == "__main__":
    start_train_queue("train_queue.yaml")
