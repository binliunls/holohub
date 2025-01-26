# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import logging
from pathlib import Path
from monai.transforms import LoadImage, SaveImage

import numpy as np
from holoscan.core import ConditionType, Fragment, Operator, OperatorSpec
from operators.medical_imaging.utils.importutil import optional_import
from operators.medical_imaging.core.domain import Image

SimpleITK, _ = optional_import("SimpleITK")


class NiftiDataLoader(Operator):
    """
    This operator reads a nifti image, extracts the numpy array and forwards it to the next operator

    Named input:
        image_path: Path to the image file, optional. Use it to override the input path set on the object.

    Named output:
        image: A Numpy array object. Downstream receiver optional.
    """

    def __init__(
        self, fragment: Fragment, *args, input_path: Path, use_monai: bool = False, **kwargs
    ) -> None:
        """Creates an instance with the file path to load image from.

        Args:
            fragment (Fragment): An instance of the Application class which is derived from Fragment.
            input_path (Path): The file Path to read from, overridden by valid named input on compute.
        """
        self._logger = logging.getLogger("{}.{}".format(__name__, type(self).__name__))
        self.input_path = input_path  # Allow to be None, to be overridden when compute is called.
        self.input_name_path = "image_path"
        self.output_name_image = "image"
        self.use_monai = use_monai
        # Need to call the base class constructor last
        super().__init__(fragment, *args, **kwargs)

    def setup(self, spec: OperatorSpec):
        spec.input(self.input_name_path).condition(ConditionType.NONE)
        spec.output(self.output_name_image).condition(
            ConditionType.NONE
        )  # Fine for no or not-ready receiver ports.

    def compute(self, op_input, op_output, context):
        """Performs computation with the provided context."""

        # The named input port is optional, so must check for and validate the data
        input_path = None
        try:
            input_path = op_input.receive(self.input_name_path)
        except Exception:
            pass

        if not input_path or not Path(input_path).is_file:
            self._logger.info(f"No or invalid file path from the optional input port: {input_path}")
            # Try to fall back to use the object attribute if it is valid
            if self.input_path and self.input_path.is_file():
                input_path = self.input_path
            else:
                raise ValueError(
                    f"No valid file path from input port or obj attribute: {self.input_path}"
                )
        image_np = self.convert_and_save(input_path)
        op_output.emit(image_np, self.output_name_image)

    def convert_and_save(self, nii_path):
        """
        reads the nifti image and returns a numpy image array
        """
        if self.use_monai:
            image_reader = LoadImage()
            image_np = image_reader(nii_path)
            image_np = Image(image_np.numpy(), image_np.meta)
        else:
            image_reader = SimpleITK.ImageFileReader()
            image_reader.SetFileName(str(nii_path))
            image = image_reader.Execute()
            image_np = np.transpose(SimpleITK.GetArrayFromImage(image), [2, 1, 0])
        return image_np


class NiftiDataWriter(Operator):
    """
    This operator writes a numpy array to a local path as the NIfTI format.

    Named input:
        image_path: Path to save the image file.
    """

    INPUT_NAME = "input_dict"

    def __init__(
        self, fragment: Fragment, *args, image_path: Path, save_key: str="pred", use_monai=False, **kwargs
    ) -> None:
        """Creates an instance with the file path to save image to.

        Args:
            fragment (Fragment): An instance of the Application class which is derived from Fragment.
            image_path (Path): The file Path to write to.
        """
        self._logger = logging.getLogger("{}.{}".format(__name__, type(self).__name__))
        self.image_path = image_path  # Allow to be None, to be overridden when compute is called.
        self.save_key = save_key
        self.use_monai = use_monai
        # Need to call the base class constructor last
        super().__init__(fragment, *args, **kwargs)

    def setup(self, spec: OperatorSpec):
        spec.input(self.INPUT_NAME).condition(ConditionType.NONE)

    def compute(self, op_input, op_output, context):
        """Performs computation with the provided context."""

        # The named input port is optional, so must check for and validate the data
        input_dict = op_input.receive(self.INPUT_NAME)
        input_res = input_dict[0]
        pred_array = input_res.get(self.save_key, None)
        self.convert_and_save(pred_array)

    def convert_and_save(self, np_array):
        """
        reads the nifti image and returns a numpy image array
        """
        if self.use_monai:
            image_saver = SaveImage(self.image_path)
            image_saver(np_array)
        else:
            nii_image = SimpleITK.GetImageFromArray(np_array)
            # Save the SimpleITK image as a NIfTI file
            SimpleITK.WriteImage(nii_image, self.image_path)


def test():
    # Make sure the file path is correct.
    filepath = (
        Path(__file__).parent.resolve()
        / "../../../inputs/lung_seg_ct/nii/volume-covid19-A-0001.nii"
    )
    fragment = Fragment()
    nii_operator = NiftiDataLoader(fragment, input_path=filepath)
    _ = nii_operator.convert_and_save(filepath)


def main():
    test()


if __name__ == "__main__":
    main()
