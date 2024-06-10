from lr_scheduler import get_custom_lr_scheduler, get_fixed_lr_scheduler
from run_manager import RunManager, load_checkpoint

import argparse
import os
import torch
import data_setup
import engine
import model_builder
from torchvision import transforms
import yaml
config = yaml.safe_load(open("config.yaml"))

# to call this script, run the following command:
# start with learning rate 0.01 to speed the fuck out of the training. if it starts to bounce around, then we can decrease it.
# python train.py --num_epochs 10 --batch_size 32 --hidden_units 128 --learning_rate 0.01 --run_id cpu_run_on_image_net

# GPU training command:
# python train.py --num_epochs 50 --batch_size 128 --hidden_units 256 --learning_rate 0.001 --run_id cuda_run_with_256_hidden_units --device cuda

# python train.py --num_epochs 100 --batch_size 1024 --hidden_units 256 --learning_rate 0.005 --run_id image_net_train_deeper_network_and_dropout --device cuda


def train(args) -> None:

    # Setup target device
    assert args.device in ["cpu", "cuda"], "Invalid device"

    if args.device == "cuda" and not torch.cuda.is_available():
        raise Exception("CUDA is not available on this device")

    # yolo uses 448x448 images
    # Create transforms
    data_transform = transforms.Compose([
        # transforms.RandomResizedCrop(50),
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(30),
        transforms.ColorJitter(brightness=0.5, contrast=0.5),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
        # transforms.RandomErasing()
    ])

    classes = ["n01986214", "n02009912", "n01924916"]

    # cpu_count = os.cpu_count()
    # num_workers = cpu_count if cpu_count is not None else 0
    num_workers = 8

    # Create DataLoaders with help from data_setup.py
    train_dataloader, test_dataloader = data_setup.create_dataloaders(
        root_dir=config["image_net_data_dir"],
        transform=data_transform,
        batch_size=args.batch_size,
        num_workers=num_workers
    )
    # print('input data shape is', next(iter(train_dataloader))[0].shape)
    # input()

    # Create model with help from model_builder.py
    model = model_builder.DeepConvNet().to(args.device)

    run_manager = RunManager(args.run_id)
    if args.continue_from_checkpoint_run_id is not None and args.continue_from_checkpoint_path is None:
        epoch_start = load_checkpoint(
            model, run_id=args.continue_from_checkpoint_run_id, checkpoint_path=args.continue_from_checkpoint_path)
    else:
        epoch_start = 0

    # Set loss and optimizer
    loss_fn = torch.nn.CrossEntropyLoss()

    optimizer = torch.optim.Adam(model.parameters(),
                                 lr=0.001)

    if args.lr_scheduler == "custom":
        lr_scheduler = get_custom_lr_scheduler(optimizer)
    else:
        lr_scheduler = get_fixed_lr_scheduler(optimizer, lr=float(args.lr))

    parameters = {
        "num_epochs": args.num_epochs,
        "lr_scheduler": args.lr_scheduler,
        "batch_size": args.batch_size,
        "loss_fn": "CrossEntropyLoss",
        "optimizer": "Adam",
        "device": args.device,
    }

    run_manager.log_data({"parameters": parameters,
                          "model/summary": str(model),
                          })

    run_manager.log_files({"model/code": "model_builder.py",
                           "lr_scheduler/code": "lr_scheduler.py",
                           })

    engine.train(model=model,
                 train_dataloader=train_dataloader,
                 val_dataloader=test_dataloader,
                 lr_scheduler=lr_scheduler,
                 optimizer=optimizer,
                 loss_fn=loss_fn,
                 epoch_start=epoch_start,
                 epoch_end=epoch_start + args.num_epochs,
                 k_top=5,
                 run_manager=run_manager,
                 checkpoint_interval=args.checkpoint_interval,
                 log_interval=args.log_interval,
                 device=args.device)

    run_manager.end_run()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        prog='Computer Vision Model Trainer',
        description='Trains a computer vision model for image classification',
        epilog='Enjoy the program! :)')

    parser.add_argument('--num_epochs', type=int, required=True,
                        help='Number of epochs to train the model')
    parser.add_argument('--batch_size', type=int, required=True,
                        help='Batch size for training the model')
    parser.add_argument('--lr_scheduler', type=str, required=True,
                        help='Scheduler for the optimizer or custom')
    parser.add_argument('--run_id', type=str, required=True,
                        help='Unique identifier for the run')

    parser.add_argument('--log_interval', type=int, default=10,
                        help='The number of batches to wait before logging training status')
    parser.add_argument('--checkpoint_interval', type=int, default=1,
                        help='The number of epochs to wait before saving model checkpoint')
    parser.add_argument('--continue_from_checkpoint_run_id', type=str, default=None,
                        help='Run ID to continue training from')
    parser.add_argument('--continue_from_checkpoint_path', type=str, default=None,
                        help='Checkpoint path for the run continue training from')
    parser.add_argument('--device', type=str, default="cpu",
                        help='Device to train the model on')
    parser.add_argument('--train_dir', type=str, default=f'{config["image_net_data_dir"]}/train',
                        help='Directory containing training data')
    parser.add_argument('--val_dir', type=str, default=f'{config["image_net_data_dir"]}/val',
                        help='Directory containing validation data')
    # parser.add_argument('--run_dir', type=str, default=config["run_dir"],
    # help='Directory to store runs')

    args = parser.parse_args()

    try:
        inp = input(f"Confirm that run_id is {args.run_id}: yes or no: ")

        if inp.lower() != "yes":
            raise Exception("Type yes on input...")

        print("Starting training for run_id:", args.run_id)
        train(args)

    except KeyboardInterrupt:
        # without this: weird issues where KeyboardInterrupt causes a ton of torch_smh_manager processes that never close.
        print("Training interrupted by user")
