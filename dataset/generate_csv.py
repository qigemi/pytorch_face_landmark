import cv2
import os
import random
train_anno = '/media/qigemi/data/MTFL/training.txt'
test_anno = '/media/qigemi/data/MTFL/testing.txt'

items = []
with open(train_anno) as anno_file:
    lines = anno_file.readlines()
    for line in lines:
        line = line.split(' ')[1:12]
        items.append(','.join(line)+'\n')
with open('face_landmark_train.csv','w') as trainfile:
    for item in items:
        trainfile.write(item)

items = []
with open(test_anno) as anno_file:
    lines = anno_file.readlines()
    for line in lines:
        line = line.split(' ')[1:12]
        items.append(','.join(line)+'\n')
with open('face_landmark_val.csv','w') as valfile:
    for item in items:
        valfile.write(item)
