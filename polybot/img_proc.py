from pathlib import Path
import random

from matplotlib.image import imread, imsave


def rgb2gray(rgb):
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    gray = 0.2989 * r + 0.5870 * g + 0.1140 * b
    return gray


class Img:

    def __init__(self, path):
        """
        Do not change the constructor implementation
        """
        self.path = Path(path)
        self.data = rgb2gray(imread(path)).tolist()

    def save_img(self):
        """
        Do not change the below implementation
        """
        new_path = self.path.with_name(self.path.stem + '_filtered' + self.path.suffix)
        imsave(new_path, self.data, cmap='gray')
        return new_path

    def blur(self, blur_level=16):

        height = len(self.data)
        width = len(self.data[0])
        filter_sum = blur_level ** 2

        result = []
        for i in range(height - blur_level + 1):
            row_result = []
            for j in range(width - blur_level + 1):
                sub_matrix = [row[j:j + blur_level] for row in self.data[i:i + blur_level]]
                average = sum(sum(sub_row) for sub_row in sub_matrix) // filter_sum
                row_result.append(average)
            result.append(row_result)

        self.data = result

    def contour(self):
        for i, row in enumerate(self.data):
            res = []
            for j in range(1, len(row)):
                res.append(abs(row[j-1] - row[j]))

            self.data[i] = res

    def rotate(self):
        for i in range(len(self.data)):
            for j in range(i,len(self.data[0])):
                self.data[i][j] , self.data[j][i] = self.data[j][i] , self.data[i][j]
        for row in self.data:
            row.reverse()

    def rotate2(self):
        self.rotate()
        self.rotate()


    def salt_n_pepper(self):
        for i in range(len(self.data)):
            for j in range(len(self.data[0])):
                random_number = random.random()
                if random_number < 0.2:
                    self.data[i][j] = 255
                elif random_number > 0.8:
                    self.data[i][j] = 0

    def concat(self, other_img, direction='horizontal'):
        if direction=='horizontal':
            if len(self.data) != len(other_img.data):
                raise RuntimeError("images must have the same height")

            new_data = []
            for row_self, row_other in zip(self.data, other_img.data):
                new_row = row_self + row_other
                new_data.append(new_row)

            self.data = new_data
        elif direction=='vertical':
            if len(self.data[0]) != len(other_img.data[0]):
                raise RuntimeError("images must have the same width")

            self.data = self.data + other_img.data

        else:
            raise RuntimeError("direction must be either 'horizontal' or 'vertical'")


    def segment(self):
        for i in range(len(self.data)):
            for j in range(len(self.data[0])):
                if self.data[i][j] > 100 :
                    self.data[i][j]  = 255
                else:
                    self.data[i][j] = 0

    def brighten(self, value=30):
        for i in range(len(self.data)):
            for j in range(len(self.data[0])):
                self.data[i][j] = min(255, self.data[i][j] + value)

    def darken(self, value=30):
        for i in range(len(self.data)):
            for j in range(len(self.data[0])):
                self.data[i][j] = max(0, self.data[i][j] - value)

    def invert(self):
        for i in range(len(self.data)):
            for j in range(len(self.data[0])):
                self.data[i][j] = 255 - self.data[i][j]


