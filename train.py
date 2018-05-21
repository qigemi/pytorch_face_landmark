'''
Training script for CIFAR-10/100
Copyright (c) Wei YANG, 2017
'''
from __future__ import print_function

import argparse
import os
import shutil
import time
import random

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torch.utils.data as data
import torchvision.transforms as transforms
import torchvision.datasets as datasets
from models import *
from dataset.FaceLandmarksDataset import *

from utils import Bar, Logger, AverageMeter,normalizedME, mkdir_p, savefig


parser = argparse.ArgumentParser(description='PyTorch face landmark Training')
# Datasets
parser.add_argument('-d', '--dataset', default='face5', type=str)
parser.add_argument('-j', '--workers', default=8, type=int, metavar='N',
                    help='number of data loading workers (default: 4)')
# Optimization options
parser.add_argument('--epochs', default=10, type=int, metavar='N',
                    help='number of total epochs to run')
parser.add_argument('--start-epoch', default=0, type=int, metavar='N',
                    help='manual epoch number (useful on restarts)')
parser.add_argument('--sigma', default=1, type=int, metavar='N')
parser.add_argument('--point-size', default=5, type=int, metavar='N')
parser.add_argument('--img-size', default=64, type=int, metavar='N')

parser.add_argument('--train-batch', default=4, type=int, metavar='N',
                    help='train batchsize')
parser.add_argument('--test-batch', default=1, type=int, metavar='N',
                    help='test batchsize')
parser.add_argument('--lr', '--learning-rate', default=0.0001, type=float,
                    metavar='LR', help='initial learning rate')
parser.add_argument('--drop', '--dropout', default=0, type=float,
                    metavar='Dropout', help='Dropout ratio')
parser.add_argument('--schedule', type=int, nargs='+', default=[60,100],
                        help='Decrease learning rate at these epochs.')
parser.add_argument('--gamma', type=float, default=0.1, help='LR is multiplied by gamma on schedule.')
parser.add_argument('--momentum', default=0.9, type=float, metavar='M',
                    help='momentum')
parser.add_argument('--weight-decay', '--wd', default=5e-4, type=float,
                    metavar='W', help='weight decay (default: 1e-4)')
# Checkpoints
parser.add_argument('-c', '--checkpoint', default='checkpoint/2/', type=str, metavar='PATH',
                    help='path to save checkpoint (default: checkpoint)')
#parser.add_argument('--resume', default='/home/foto1/workspace/zuoxin/face_landmark/checkpoint/0918/facelandmark_squeezenet_128_55.pth.tar', type=str, metavar='PATH',
#                    help='path to latest checkpoint (default: none)')
parser.add_argument('--resume', default='', type=str, metavar='PATH',
                    help='path to latest checkpoint (default: none)')
# Architecture
parser.add_argument('--depth', type=int, default=104, help='Model depth.')
parser.add_argument('--cardinality', type=int, default=8, help='Model cardinality (group).')
parser.add_argument('--widen-factor', type=int, default=4, help='Widen factor. 4 -> 64, 8 -> 128, ...')
parser.add_argument('--growthRate', type=int, default=12, help='Growth rate for DenseNet.')
parser.add_argument('--compressionRate', type=int, default=2, help='Compression Rate (theta) for DenseNet.')
# Miscs
parser.add_argument('--manualSeed', type=int, help='manual seed')
parser.add_argument('-e', '--evaluate', dest='evaluate', action='store_true',
                    help='evaluate model on validation set')
#Device options
parser.add_argument('--gpu_id', default='0', type=str,
help='id(s) for CUDA_VISIBLE_DEVICES')

args = parser.parse_args()
state = {k: v for k, v in args._get_kwargs()}


# Use CUDA
os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu_id
use_cuda = torch.cuda.is_available()

# Random seed
if args.manualSeed is None:
    args.manualSeed = random.randint(1, 10000)
random.seed(args.manualSeed)
torch.manual_seed(args.manualSeed)
if use_cuda:
    torch.cuda.manual_seed_all(args.manualSeed)

best_acc= 999  # best test accuracy

def main():
    global best_acc
    start_epoch = args.start_epoch  # start from epoch 0 or last checkpoint epoch

    if not os.path.isdir(args.checkpoint):
        mkdir_p(args.checkpoint)

    # Data
    print('==> Preparing dataset %s' % args.dataset)
    transform_train = transforms.Compose([
        Rescale((74,74)),
        RandomCrop((64,64)),
        RandomFlip(),
        #RandomContrast(),
        RandomBrightness(),
        RandomLightingNoise(),
        ToTensor(64),
        Normalize([ 0.485, 0.456, 0.406 ],
                          [ 0.229, 0.224, 0.225 ]),
    ])

    transform_test = transforms.Compose([
        #SmartRandomCrop(),
        Rescale((64,64)),
        ToTensor(64),
        Normalize([ 0.485, 0.456, 0.406 ],
                           [ 0.229, 0.224, 0.225 ]),
    ])

    trainset = FaceLandmarksDataset(csv_file='dataset/face_landmark_train.csv', transform=transform_train,root_dir='/media/qigemi/data/MTFL')
    trainloader = data.DataLoader(trainset, batch_size=args.train_batch, shuffle=True, num_workers=args.workers)

    testset = FaceLandmarksDataset(csv_file='dataset/face_landmark_val.csv', transform=transform_test,root_dir='/media/qigemi/data/MTFL')
    testloader = data.DataLoader(testset, batch_size=args.train_batch, shuffle=True, num_workers=args.workers)

    model = UNet(3,5)
    params = torch.load('/home/qigemi/project/human_pose/Pytorch-UNet/MODEL.pth')
    model.load_state_dict(params)
    #print('success!!!\n')
    cudnn.benchmark = True
    print('    Total params: %.2fM' % (sum(p.numel() for p in model.parameters())/1000000.0))

    criterion = nn.MSELoss().cuda()
    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)
    #ignored_params = list(map(id, model.fc.parameters()))
    #base_params = filter(lambda p: id(p) not in ignored_params,
    #                     model.parameters())
    #params = [
    #    {'params': base_params, 'lr': args.lr},
    #    {'params': model.fc.parameters(), 'lr': args.lr * 10}
    #]
    model = torch.nn.DataParallel(model).cuda()
    #optimizer = optim.Adam(params=params, lr=args.lr, weight_decay=args.weight_decay)

    # Resume
    title = 'facelandmark_hourglass'
    if args.resume:
        # Load checkpoint.
        print('==> Resuming from checkpoint..')
        assert os.path.isfile(args.resume), 'Error: no checkpoint directory found!'
        args.checkpoint = os.path.dirname(args.resume)
        checkpoint = torch.load(args.resume)
        best_acc = checkpoint['best_acc']
        start_epoch = checkpoint['epoch']
        model.load_state_dict(checkpoint['state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer'])
        if os.path.exists(os.path.join(args.checkpoint, title+'_log.txt')):
            logger = Logger(os.path.join(args.checkpoint, title+'_log.txt'), title=title, resume=True)
        else:
            logger = Logger(os.path.join(args.checkpoint, title+'_log.txt'), title=title)
            logger.set_names(['Learning Rate', 'Train Loss', 'Train Acc.'])
    else:
        logger = Logger(os.path.join(args.checkpoint, title+'_log.txt'), title=title)
#        logger.set_names(['Learning Rate', 'Train Loss', 'Valid Loss', 'Train Acc.', 'Valid Acc.'])
        logger.set_names(['Learning Rate', 'Train Loss', 'Train Acc.'])


    if args.evaluate:
        print('\nEvaluation only')
        model.load_state_dict(torch.load('checkpoint/2/model_best.pth.tar')['state_dict'])
        test_loss, test_acc = test(testloader, model, criterion, start_epoch, use_cuda)
        print(' Test Loss:  %.8f, Test Acc:  %.2f' % (test_loss, test_acc))
        return

    # Train and val
    for epoch in range(start_epoch, args.epochs):
        adjust_learning_rate(optimizer, epoch)

        print('\nEpoch: [%d | %d] LR: %f' % (epoch + 1, args.epochs, state['lr']))

        train_loss, train_acc = train(trainloader, model, criterion, optimizer, epoch, use_cuda)
#        test_loss, test_acc = test(testloader, model, criterion, epoch, use_cuda)

        # append logger file
        logger.append([state['lr'], train_loss, train_acc])

        # save model
        is_best = train_loss <best_acc
        best_acc =min(train_loss, best_acc)
        save_checkpoint({
                'epoch': epoch + 1,
                'state_dict': model.state_dict(),
                'acc': train_acc,
                'best_acc': best_acc,
                'optimizer' : optimizer.state_dict(),
            }, is_best, checkpoint=args.checkpoint,filename=title+'_'+str(epoch)+'.pth.tar')


    logger.close()
    logger.plot()
    savefig(os.path.join(args.checkpoint, 'log.eps'))

    print('Best acc:')
    print(best_acc)

def putGaussian(gt,x,y):
    #print(x,y)
    y_range = [i for i in range(args.img_size)]
    x_range = [i for i in range(args.img_size)]
    xx, yy = np.meshgrid(x_range, y_range)
    d2 = (xx - y) ** 2 + (yy - x) ** 2
    exponent = d2 / 2.0 / args.sigma / args.sigma
    heatmap = np.exp(-exponent)
    gt = gt + heatmap
    return gt

def train(trainloader, model, criterion, optimizer, epoch, use_cuda):
    # switch to train mode
    model.train()
    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    NormMS = AverageMeter()
    end = time.time()

    bar = Bar('Processing', max=len(trainloader))
    for batch_idx, batch_data in enumerate(trainloader):
        # measure data loading time
        data_time.update(time.time() - end)
        inputs = batch_data['image']
        targets = batch_data['landmarks']
        inputs = torch.autograd.Variable(inputs)
        if use_cuda:
            inputs = inputs.cuda()

        # compute output
        outputs = model(inputs)#output.shape = (n,5,64,64)
        gt = np.zeros(outputs.shape)
        for i,face in enumerate(targets):
            for j in range(outputs.shape[1]):
                x = face[j*2]*args.img_size
                y = face[j*2+1]*args.img_size
                gt[i][j] = putGaussian(gt[i][j],x,y)
        gt = torch.from_numpy(gt.astype(np.float32))
        #print(outputs.shape, gt.shape)
        gt = torch.autograd.Variable(gt)
        if use_cuda:
            gt = gt.cuda()

        loss = criterion(outputs, gt)

        gt=gt.cpu().data.numpy()
        outputs = outputs.cpu().data.numpy()
        cv2.imshow('groundtruth',gt[0][0])
        cv2.imshow('result',outputs[0][0])
        cv2.waitKey(200)

        # measure accuracy and record loss
        #nms= normalizedME(outputs.data,targets.data,64,64)
        losses.update(loss.data[0], inputs.size(0))
        #NormMS.update(nms[0], inputs.size(0))

        # compute gradient and do SGD step
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()

        # plot progress
        bar.suffix  = '({batch}/{size}) Data: {data:.3f}s | Batch: {bt:.3f}s | Total: {total:} | ETA: {eta:} | Loss: {loss:.4f}'.format(
                    batch=batch_idx + 1,
                    size=len(trainloader),
                    data=data_time.avg,
                    bt=batch_time.avg,
                    total=bar.elapsed_td,
                    eta=bar.eta_td,
                    loss=losses.avg,
                    )
        bar.next()
    bar.finish()
    return (losses.avg,0)

def test(testloader, model, criterion, epoch, use_cuda):
    global best_acc

    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()

    # switch to evaluate mode
    model.eval()

    end = time.time()
    bar = Bar('Processing', max=len(testloader))
    for batch_idx, batch_data in enumerate(testloader):
        # measure data loading time
        data_time.update(time.time() - end)

        inputs = batch_data['image']
        targets = batch_data['landmarks']
        if use_cuda:
            inputs = inputs.cuda()
        inputs = torch.autograd.Variable(inputs)

        # compute output
        outputs = model(inputs)#output.shape = (n,5,64,64)
        gt = np.zeros(outputs.shape)
        for i,face in enumerate(targets):
            for j in range(outputs.shape[1]):
                x = face[j*2]*args.img_size
                y = face[j*2+1]*args.img_size
                gt[i][j] = putGaussian(gt[i][j],x,y)
        gt = torch.from_numpy(gt.astype(np.float32))
        #print(outputs.shape, gt.shape)
        if use_cuda:
            gt = gt.cuda()
        gt = torch.autograd.Variable(gt)
        loss = criterion(outputs, gt)

        gt=gt.cpu().data.numpy()
        outputs = outputs.cpu().data.numpy()
        cv2.imshow('groundtruth',gt[0][0])
        cv2.imshow('result',outputs[0][0])
        cv2.waitKey(0)

        # measure accuracy and record loss
        losses.update(loss.data[0], inputs.size(0))

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()

        # plot progress
        bar.suffix  = '({batch}/{size}) Data: {data:.3f}s | Batch: {bt:.3f}s | Total: {total:} | ETA: {eta:} | Loss: {loss:.4f} '.format(
                    batch=batch_idx + 1,
                    size=len(testloader),
                    data=data_time.avg,
                    bt=batch_time.avg,
                    total=bar.elapsed_td,
                    eta=bar.eta_td,
                    loss=losses.avg,
                    )
        bar.next()
    bar.finish()
    return (losses.avg,0)

def save_checkpoint(state, is_best, checkpoint='checkpoint', filename='checkpoint.pth.tar'):
    filepath = os.path.join(checkpoint, filename)
    torch.save(state, filepath)
    if is_best:
        shutil.copyfile(filepath, os.path.join(checkpoint, 'model_best.pth.tar'))

def adjust_learning_rate(optimizer, epoch):
    global state
    if epoch in args.schedule:
        state['lr'] *= args.gamma
        for param_group in optimizer.param_groups:
            param_group['lr'] = state['lr']

if __name__ == '__main__':
    main()
