import os
import pickle
import re
import time
from collections import defaultdict
from datetime import datetime

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset
from typing import Tuple, List

from tqdm import tqdm


class BirdsDataset(Dataset):
    def __init__(self, files: List[str], box: Tuple, num_past: int, diff_minutes: int, size: Tuple[int, int]):
        self.files = files
        self.box = box
        self.num_past = num_past
        self.diff_minutes = diff_minutes
        self.size = size
        self.cache_dir = "cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        self._listdirs = {}
        self.times = [datetime.strptime(re.search('--(.*)_VRADH', os.path.basename(file)).group(1).replace('-', ' '),
                                        '%Y%m%d %H%M%S').timestamp() for file in files]
        self.times = torch.tensor(self.times).long()
        time_mask = self.times[:, None] - self.times[None, :] > diff_minutes * 60
        self.relevant_indices = (time_mask.sum(dim=1) >= self.num_past).nonzero().flatten()
        self.mask_files = {file: self._get_mask_file_path(file) for file in tqdm(files)}
        for idx, rel_idx in enumerate(tqdm(self.relevant_indices.tolist())):
            item = self.get_item_old(rel_idx)
            with open(os.path.join(self.cache_dir, f"{idx}.pkl"), "wb") as f:
                pickle.dump(item, f)

    def get_item_old(self, index):
        imgs = [self._load_img(self.files[index - i]) for i in range(self.num_past + 1)]
        label = self._load_annotation(self.files[index])
        return torch.concatenate(imgs, dim=2).permute(2, 0, 1), label

    def __getitem__(self, index):
        with open(os.path.join(self.cache_dir, f"{index}.pkl"), "rb") as f:
            return pickle.load(f)

    def _load_img(self, file):
        image_prev = Image.open(file)
        image_prev = image_prev.crop(self.box)
        image_prev = image_prev.resize(self.size)
        img_numpy = np.array(image_prev) / 255.0
        return torch.from_numpy(img_numpy)

    def _load_annotation(self, file):
        mask_file = self.mask_files[file]
        if mask_file is None:
            mask = np.zeros((256, 256), dtype=np.uint8)
        else:
            mask = Image.open(mask_file).convert('L')
            mask = mask.crop(self.box)
            mask = np.array(mask.resize(self.size))
            mask[mask != 0] = 1

        return torch.from_numpy(mask)[None, ...]

    def _get_mask_file_path(self, file):
        f_path = os.path.dirname(file)
        self._listdirs[f_path] = self._listdirs.get(f_path) or os.listdir(f_path)
        num_f = str(int(os.path.basename(file).split('-')[0]))
        mask_file = [i for i in self._listdirs[f_path] if os.path.isfile(os.path.join(f_path, i)) and
                     num_f == (os.path.basename(i).split('-')[0]) and '.png' in i]
        if len(mask_file) == 0:
            return None
        mask_file = str(mask_file)[2:-2]
        return os.path.join(f_path, mask_file)

    def __len__(self):
        return len(self.relevant_indices)