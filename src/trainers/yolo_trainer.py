import torch
from torch import nn
from torch.optim import Optimizer
from torch.utils.data import DataLoader
from tqdm import tqdm

from src import utils
from src.run_manager import RunManager


def log_gradients(model: nn.Module) -> None:
    for name, param in model.named_parameters():
        if param.grad is not None:
            avg_grad = param.grad.abs().mean().item()
            avg_weight = param.abs().mean().item()
            avg_grad_weight = avg_grad / avg_weight
            print(
                f"Layer: {name} | Avg Grad: {avg_grad} | Avg Weight: {avg_weight} | Avg Grad/Weight: {avg_grad_weight}"
            )


def train_step(
    model: nn.Module,
    dataloader: DataLoader,
    loss_fn: nn.modules.loss._Loss | nn.Module,
    optimizer: Optimizer,
    run_manager: RunManager,
    log_interval: int,
    epoch: int,
    device: str,
) -> None:
    model.train()
    train_loss = 0
    num_correct = 0
    num_incorrect_localization = 0

    num_incorrect_other = 0
    num_incorrect_background = 0
    num_predictions = 0

    for batch, (X, y) in tqdm(
        enumerate(dataloader), total=len(dataloader), desc="Train Step", leave=False
    ):
        X, y = X.to(device), y.to(device)

        y_pred = model(X)

        loss = loss_fn(y_pred, y)
        train_loss += loss.item()
        optimizer.zero_grad()
        loss.backward()
        # torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        result_dict = utils.get_yolo_metrics(y_pred, y)

        num_correct += result_dict["num_correct"]
        num_incorrect_localization += result_dict["num_incorrect_localization"]
        num_incorrect_other += result_dict["num_incorrect_other"]
        num_incorrect_background += result_dict["num_incorrect_background"]

        num_predictions += len(y)

        log_gradients(model)

        if batch != 0 and batch % log_interval == 0:
            run_manager.log_metrics(
                {
                    "train/loss": loss.item(),
                    "train/accuracy": num_correct / num_predictions,
                    "train/percent_incorrect_localization": num_incorrect_localization
                    / num_predictions,
                    "train/percent_incorrect_other": num_incorrect_other
                    / num_predictions,
                    "train/percent_incorrect_background": num_incorrect_background
                    / num_predictions,
                },
                epoch + batch / len(dataloader),
            )
            num_correct = 0
            num_incorrect_localization = 0

            num_incorrect_other = 0
            num_incorrect_background = 0
            num_predictions = 0


def test_step(
    model: nn.Module,
    dataloader: DataLoader,
    loss_fn: nn.modules.loss._Loss | nn.Module,
    run_manager: RunManager,
    epoch: int,
    device: str,
) -> None:
    model.eval()

    test_loss = 0
    num_correct = 0
    num_incorrect_localization = 0
    num_incorrect_other = 0
    num_incorrect_background = 0
    num_predictions = 0

    with torch.inference_mode():
        for batch, (X, y) in tqdm(
            enumerate(dataloader), total=len(dataloader), desc="Test Step", leave=False
        ):
            X, y = X.to(device), y.to(device)

            y_pred = model(X)

            loss = loss_fn(y_pred, y)
            test_loss += loss.item()

            result_dict = utils.get_yolo_metrics(y_pred, y)

            num_correct += result_dict["num_correct"]
            num_incorrect_localization += result_dict["num_incorrect_localization"]
            num_incorrect_other += result_dict["num_incorrect_other"]
            num_incorrect_background += result_dict["num_incorrect_background"]

            num_predictions += len(y)

    # TODO: should be val/
    run_manager.log_metrics(
        {
            "val/loss": test_loss / len(dataloader),
            "val/accuracy": num_correct / num_predictions,
            "val/percent_incorrect_localization": num_incorrect_localization
            / num_predictions,
            "val/percent_incorrect_other": num_incorrect_other / num_predictions,
            "val/percent_incorrect_background": num_incorrect_background
            / num_predictions,
        },
        epoch,
    )


def train(
    model: torch.nn.Module,
    train_dataloader: DataLoader,
    val_dataloader: DataLoader,
    lr_scheduler: torch.optim.lr_scheduler.LRScheduler,
    optimizer: torch.optim.Optimizer,
    loss_fn: nn.modules.loss._Loss | nn.Module,
    epoch_start: int,
    epoch_end: int,
    run_manager: RunManager,
    checkpoint_interval: int,
    log_interval: int,
    device: str,
):
    """
    Train a PyTorch model.

    Args:
        model: A PyTorch model to train.
        train_dataloader: A PyTorch DataLoader for training data.
        val_dataloader: A PyTorch DataLoader for validation data.
        lr_scheduler: A PyTorch learning rate scheduler.
        optimizer: A PyTorch optimizer to use for training.
        loss_fn: A PyTorch loss function to use for training.
        epoch_start: The starting epoch for training.
        epoch_end: The ending epoch for training.
        run_manager: An instance of the RunManager class for logging metrics.
        checkpoint_interval: The interval at which to save model checkpoints.
        log_interval: The interval at which to log metrics.
        device: The device to run the model on.

    """

    run_manager.log_metrics(
        {"learning_rate": optimizer.param_groups[0]["lr"]}, epoch_start
    )

    for epoch in tqdm(range(epoch_start, epoch_end), desc="Epochs"):
        train_step(
            model,
            train_dataloader,
            loss_fn,
            optimizer,
            run_manager,
            log_interval,
            epoch,
            device,
        )
        test_step(model, val_dataloader, loss_fn, run_manager, epoch + 1, device)

        run_manager.log_metrics(
            {"learning_rate": optimizer.param_groups[0]["lr"]},
            epoch + 1,
        )

        # saves model/epoch_5 at the end of epoch 5. epochs are 0 indexed.
        if epoch % checkpoint_interval == 0 or epoch == epoch_end - 1:
            run_manager.save_model(model, epoch)

        lr_scheduler.step()
