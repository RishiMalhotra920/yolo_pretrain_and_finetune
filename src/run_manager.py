import shutil
from pathlib import Path
from typing import Any, Dict

import neptune
import torch
import yaml

config = yaml.safe_load(open("config.yaml"))


class RunManager:
    """
    The job of the run manager is to manage experiment runs. It integrates
    """

    def __init__(
        self,
        *,
        new_run_name: str | None = None,
        load_from_run_id: str | None = None,
        tags: list[str] = [],
        source_files: list[str] = [],
    ):
        self.temp_dir = Path("temp")
        self.temp_dir.mkdir(exist_ok=True)

        assert new_run_name is not None, "new_run_name should not be None"
        self.run = neptune.init_run(
            project="towards-hi/image-classification",
            api_token=config["neptune_api_token"],
            name=new_run_name,
            source_files=source_files,
            tags=tags,
        )

    def add_tags(self, tags: list[str]) -> None:
        """
        Add tags to the run.

        Args:
          tags: a list of tags to add to the run.

        Example:
          tags = ["resnet", "cifar10"]
        """
        self.run["sys/tags"].add(tags)

    def set_checkpoint_to_continue_from(
        self, checkpoint_to_continue_from_signature: str
    ) -> None:
        """
        Set the checkpoint to continue from.

        Args:
          checkpoint_to_continue_from_signature: a string in the format RunId:CheckpointPath
        """
        self.log_data(
            {
                "checkpoint_to_continue_from_signature": checkpoint_to_continue_from_signature
            }
        )

    def log_data(self, data: Dict[str, Any]) -> None:
        """
        Log data to the run.

        Args:
          data: a dictionary of data to log.

        Example:
          data = {
            "num_epochs": 10,
            "learning_rate": 0.001,
            "batch_size": 32,
            "hidden_units": 512,
            "loss_fn": "CrossEntropyLoss",
            "optimizer": "Adam",
            "device": "cuda"
          }
        """
        for key in data:
            self.run[key] = data[key]

    def log_filesets(self, fileset_map: Dict[str, list[str]]) -> None:
        """
        Log filesets to the run.

        Args:
          filesets: a dictionary of filesets to log.

        Example:
          filesets = {
            "model": ["model_builder.py", "model_trainer.py"],
            "data": ["data_loader.py", "models/*.py", "data_loaders"]
          }
          you can use wildcards to upload all files in a directory
          or directory names!
        """

        for fileset_name in fileset_map:
            self.run[fileset_name].upload_files(fileset_map[fileset_name])

    def log_files(self, files: Dict[str, str]) -> None:
        """
        Log files to the run.

        Args:
          files: a dictionary of files to log.

        Example:
          files = {
            "model/code": "model_builder.py"
          }
        """
        for key in files:
            self.run[key].upload(files[key])

    def log_metrics(self, metrics: Dict[str, float], epoch: float) -> None:
        """
        Track metrics for the run and plot it on neptune.

        epoch can be a float - a float epoch denotes that we are logging a fraction of the way through the epoch

        Args:
          metrics: a dictionary of metrics to track.

        Example:
          metrics = {
            "train/loss": 0.5,
            "val/loss": 0.3,
            "train/accuracy": 0.8,
            "val/accuracy": 0.9
          }
        """

        for metric_name in metrics:
            self.run[metric_name].append(metrics[metric_name], step=epoch)
            # print(f"\nEpoch: {epoch}, {metric_name}: {metrics[metric_name]}")

    def end_run(self):
        self.run.stop()
        try:
            shutil.rmtree(self.temp_dir)

        except Exception as e:
            print(f"Failed to remove directory: {e}")

    def save_model(self, model: torch.nn.Module, epoch: int) -> None:
        """Saves a PyTorch model to a target directory.

        Args:
          model: A target PyTorch model to save.
          epoch: The epoch number to save the model at.

        Example usage:
          save_model(model=model_0, epoch=5)
        """
        # Note that model should be saved as epoch_{epoch}.pth
        # to add more info, do this: epoch_{epoch}_lr_{lr}_bs_{bs}.pth
        # later on you can implement a json file to store info about checkpoints

        # need this here in case temp dir is deleted between run creation and model saving
        self.temp_dir.mkdir(exist_ok=True)
        model_save_path = self.temp_dir / f"{epoch}.pth"
        print(f"[INFO] Saving model to {model_save_path}")
        torch.save(obj=model.state_dict(), f=model_save_path)
        self.run[f"checkpoints/epoch_{epoch}"].upload(str(model_save_path))


def load_checkpoint(model: torch.nn.Module, checkpoint_signature: str) -> int:
    """
    Loads a PyTorch model weights from a run at an epoch.
    Args:
        model: A target PyTorch model to load.
        epoch: The epoch number to load the model from.

    Example usage:
        load_model(model=model_0, epoch=5)
    """
    assert (
        ":" in checkpoint_signature
    ), "checkpoint_signature should be in the format RunId:CheckpointPath"
    run_id, checkpoint_path = checkpoint_signature.split(":")
    assert not checkpoint_path.endswith(
        ".pth"
    ), "checkpoint_path should not end with .pth"

    # save to temp_dir/{file_name}.pth
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    run = neptune.init_run(
        project="towards-hi/image-classification",
        with_id=run_id,
        mode="read-only",
        api_token=config["neptune_api_token"],
    )
    run[checkpoint_path].download(destination=str(temp_dir))

    # load from temp_dir/{file_name}.pth into model
    file_name = checkpoint_path.split("/")[-1]
    params = torch.load(temp_dir / f"{file_name}.pth", map_location=torch.device("cpu"))
    model.load_state_dict(params)

    # file_name should be epoch_{epoch}.pth
    epoch_number = int(file_name.split("_")[1])

    # we save logs for the epoch number that was completed
    # we should start logging from the next epoch
    start_epoch = epoch_number + 1

    print("this is epoch_number", epoch_number)

    try:
        shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"Failed to remove directory: {e}")

    return start_epoch
