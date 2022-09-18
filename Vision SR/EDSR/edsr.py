# -*- coding: utf-8 -*-
"""EDSR.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1yiC0QrueJ7y_azmdcdvKxInbf_wyai1z
"""

import torch
import torch.nn as nn
from torch.nn import init as init


class ResBlock(nn.Module):
    def __init__(self, n_feats, res_scale=1.0):
        super(ResBlock, self).__init__()
        m = []
        for i in range(2):
            m.append(
                nn.Conv2d(
                    n_feats, n_feats, kernel_size=3, bias=True, padding=3 // 2
                )
            )
            if i == 0:
                m.append(nn.ReLU(True))
        self.body = nn.Sequential(*m)
        self.res_scale = res_scale

    def forward(self, x):
        res = self.body(x).mul(self.res_scale)
        res += x
        return res


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat=64, num_grow_ch=32):
        super(ResidualDenseBlock, self).__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)

        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        # initialization
        self.default_init_weights(
            [self.conv1, self.conv2, self.conv3, self.conv4, self.conv5], 0.1
        )

    @torch.no_grad()
    def default_init_weights(self, module_list, scale=1, bias_fill=0, **kwargs):
        if not isinstance(module_list, list):
            module_list = [module_list]
        for module in module_list:
            for m in module.modules():
                if isinstance(m, nn.Conv2d):
                    init.kaiming_normal_(m.weight, **kwargs)
                    m.weight.data *= scale
                    if m.bias is not None:
                        m.bias.data.fill_(bias_fill)
                elif isinstance(m, nn.Linear):
                    init.kaiming_normal_(m.weight, **kwargs)
                    m.weight.data *= scale
                    if m.bias is not None:
                        m.bias.data.fill_(bias_fill)
                elif isinstance(m, nn.BatchNorm2d):
                    init.constant_(m.weight, 1)
                    if m.bias is not None:
                        m.bias.data.fill_(bias_fill)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        # Emperically, we use 0.2 to scale the residual for better performance
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, num_feat, num_grow_ch=32):
        super(RRDB, self).__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        # Emperically, we use 0.2 to scale the residual for better performance
        return out * 0.2 + x

from torch import nn as nn
from torch.nn import functional as F


def make_layer(basic_block, num_basic_block, **kwarg):
    """Make layers by stacking the same blocks.
    Args:
        basic_block (nn.module): nn.module class for basic block.
        num_basic_block (int): number of blocks.
    Returns:
        nn.Sequential: Stacked blocks in nn.Sequential.
    """
    layers = []
    for _ in range(num_basic_block):
        layers.append(basic_block(**kwarg))
    return nn.Sequential(*layers)


def pixel_unshuffle(x, scale):
    b, c, hh, hw = x.size()
    out_channel = c * (scale**2)

    p2d_h = (0, 0, 1, 0)
    p2d_w = (1, 0, 0, 0)

    if hh % 2 != 0:
        x = F.pad(x, p2d_h, "reflect")
    if hw % 2 != 0:
        x = F.pad(x, p2d_w, "reflect")
    h = x.shape[2] // scale
    w = x.shape[3] // scale

    x_view = x.view(b, c, h, scale, w, scale)
    return x_view.permute(0, 1, 3, 5, 2, 4).reshape(b, out_channel, h, w)

import torch.nn as nn

class Generator(nn.Module):
    def __init__(self, cfg):
        super(Generator, self).__init__()
        scale = cfg.scale
        num_in_ch = cfg.num_in_ch
        num_out_ch = cfg.num_out_ch
        num_feat = cfg.num_feat
        num_block = cfg.num_block
        res_scale = cfg.res_scale

        self.head = nn.Conv2d(
            num_in_ch, num_feat, kernel_size=3, padding=3 // 2
        )
        body = [ResBlock(num_feat, res_scale) for _ in range(num_block)]
        self.body = nn.Sequential(*body)
        self.tail = nn.Sequential(
            nn.Conv2d(
                num_feat,
                num_feat * (scale**2),
                kernel_size=3,
                stride=1,
                padding=1,
            ),
            nn.PixelShuffle(scale),
            nn.ReLU(True),
            nn.Conv2d(num_feat, num_out_ch, kernel_size=3, stride=1, padding=1),
        )

    def forward(self, x):
        x = self.head(x)
        res = self.body(x)
        res += x
        x = self.tail(res)
        return x

class cfg:
    pass
    
cfg.scale = 4
cfg.num_in_ch = 3
cfg.num_out_ch = 3
cfg.num_feat = 64
cfg.num_block = 32
cfg.res_scale = 1.0


model = Generator(cfg)

temp = torch.randn(1, 3, 512, 512)
out = model(temp)

print(out.size())

!pip install torchsummary
from torchsummary import summary

summary(model, (3, 512, 512))
