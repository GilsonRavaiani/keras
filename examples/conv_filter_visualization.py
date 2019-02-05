'''Visualization of the filters of VGG16, via gradient ascent in input space.

This script can run on CPU in a few minutes.

Results example: http://i.imgur.com/4nj4KjN.jpg
'''
from __future__ import print_function
from typing import List, Tuple, Optional

import time
import numpy as np
from PIL import Image as pil_image
from keras.preprocessing.image import save_img
from keras.layers.convolutional import Conv2D
from keras.applications import vgg16
from keras.models import Model
from keras.engine.base_layer import Layer
from keras import backend as K


def visualize_layer(model: Model,
                    layer_name: str,
                    step: float = 1.,
                    epochs: int = 20,
                    upscaling_steps: int = 9,
                    upscaling_factor: float = 1.2,
                    output_dim: Tuple[int, int] = (412, 412)) -> None:
    """ Visualizes the most relevant filters of one conv-layer in a certain model
        Parameters:
            model: The model containing layer_name
            layer_name: The Layer to be visualized: Has to be a part of model
            step: step size for gradient ascent
            epochs: Number of iterations for gradient ascent
            upscaling_steps: Number of upscaling steps. Starting image is in this case (80, 80)
            upscaling_factor: Factor to which to slowly upgrade the image towards output_dim.
            output_dim: [img_width, img_height] The output image dimensions.
    """

    def _normalize(x: Layer) -> Layer:
        """ utility function to normalize a tensor
            Parameters:
                x: An input tensor
            Returns:
                The normalized input tensor.
        """
        return x / (K.sqrt(K.mean(K.square(x))) + K.epsilon())

    def _deprocess_image(x: np.ndarray) -> np.ndarray:
        """ util function to convert a float array into a valid uint8 image
            Parameters:
                x: A numpy-array representing the generated image
            Returns:
                A processed numpy-array, which could be used in e.g. imshow
        """
        # normalize tensor: center on 0., ensure std is 0.25
        x -= x.mean()
        x /= (x.std() + K.epsilon())
        x *= 0.25

        # clip to [0, 1]
        x += 0.5
        x = np.clip(x, 0, 1)

        # convert to RGB array
        x *= 255
        if K.image_data_format() == 'channels_first':
            x = x.transpose((1, 2, 0))
        x = np.clip(x, 0, 255).astype('uint8')
        return x

    def _process_image(x: np.ndarray, former: np.ndarray) -> np.ndarray:
        """ util function to convert a valid uint8 image back into a float array
            Parameters:
                x: A numpy-array, which could be used in e.g. imshow
                former: The former image: Need to determine the former mean and variance.
            Returns:
                A processed numpy-array representing the generated image
        """
        if K.image_data_format() == 'channels_first':
            x = x.transpose((2, 0, 1))
        return (x / 255 - 0.5) * 4 * former.std() + former.mean()

    def _generate_filter_image(input_img: Layer,
                               layer_output: Layer,
                               filter_index: int) -> Optional[Tuple[np.ndarray, float]]:
        """ Generates image for one particular filter
            Parameters:
                input_img: The input-image Tensor
                layer_output: The output-image Tensor
                filter_index: The to be processed filter number: assumed to be valid
            Returns:
                Either None if no image could be generated
                or a tuple of the image itself and the last loss
        """
        start_time = time.time()

        # we build a loss function that maximizes the activation
        # of the nth filter of the layer considered
        if K.image_data_format() == 'channels_first':
            loss = K.mean(layer_output[:, filter_index, :, :])
        else:
            loss = K.mean(layer_output[:, :, :, filter_index])

        # we compute the gradient of the input picture wrt this loss
        grads = K.gradients(loss, input_img)[0]

        # normalization trick: we normalize the gradient
        grads = _normalize(grads)

        # this function returns the loss and grads given the input picture
        iterate = K.function([input_img], [loss, grads])

        # we start from a gray image with some random noise
        intermediate_dim = tuple(int(x / (upscaling_factor ** upscaling_steps)) for x in output_dim)
        if K.image_data_format() == 'channels_first':
            input_img_data = np.random.random((1, 3, output_dim[0], output_dim[1]))
        else:
            input_img_data = np.random.random((1, output_dim[0], output_dim[1], 3))
        input_img_data = (input_img_data - 0.5) * 20 + 128

        # Slowly upscaling towards the original size prevents a dominating high-frequency
        # of the to visualized structure as it would occur if we directly compute the 412d-image
        # Behaves as a better starting point for each following dimension
        # and therefore avoids poor local minima
        for up in reversed(range(upscaling_steps)):
            # we run gradient ascent for e.g. 20 steps
            for _ in range(epochs):
                loss_value, grads_value = iterate([input_img_data])
                input_img_data += grads_value * step

                # some filters get stuck to 0, we can skip them
                if loss_value <= K.epsilon():
                    return None

            # Calulate upscaled dimension
            intermediate_dim = tuple(int(x / (upscaling_factor ** up)) for x in output_dim)
            # Upscale
            img = _deprocess_image(input_img_data[0])
            img = np.array(pil_image.fromarray(img).resize(intermediate_dim, pil_image.BICUBIC))
            input_img_data = [_process_image(img, input_img_data[0])]

        # decode the resulting input image
        img = _deprocess_image(input_img_data[0])
        end_time = time.time()
        print('Costs of filter {:3}: {:5.0f} ( {:4.2f}s )'.format(filter_index,
                                                                  loss_value,
                                                                  end_time - start_time))
        return img, loss_value

    def _draw_filters(filters: List[Tuple[np.ndarray, float]], n: Optional[int] = None) -> None:
        """ Draw the best filters in a nxn grid.
            Parameters:
                filters: A List of generated images and their corresponding losses
                         for each processed filter.
                n: dimension of the grid
        """
        if n is None:
            n = int(np.floor(np.sqrt(len(filters))))

        # the filters that have the highest loss are assumed to be better-looking.
        # we will only keep the top n*n filters.
        filters.sort(key=lambda x: x[1], reverse=True)
        filters = filters[:n * n]

        # build a black picture with enough space for
        # e.g. our 8 x 8 filters of size 412 x 412, with a 5px margin in between
        margin = 5
        width = n * output_dim[0] + (n - 1) * margin
        height = n * output_dim[1] + (n - 1) * margin
        stitched_filters = np.zeros((width, height, 3), dtype='uint8')

        # fill the picture with our saved filters
        for i in range(n):
            for j in range(n):
                img, _ = filters[i * n + j]
                width_margin = (output_dim[0] + margin) * i
                height_margin = (output_dim[1] + margin) * j
                stitched_filters[
                    width_margin: width_margin + output_dim[0],
                    height_margin: height_margin + output_dim[1], :] = img

        # save the result to disk
        save_img('vgg_{0:}_{1:}x{1:}.png'.format(layer_name, n), stitched_filters)

    # this is the placeholder for the input images
    assert len(model.inputs) == 1
    input_img: Layer = model.inputs[0]

    # get the symbolic outputs of each "key" layer (we gave them unique names).
    layer_dict = dict([(layer.name, layer) for layer in model.layers[1:]])

    output_layer: Layer = layer_dict[layer_name]
    assert isinstance(output_layer, Conv2D)

    # iterate through each filter and generate its corresponding image
    processed_filters: List[Tuple[np.ndarray, float]] = []
    for f in range(len(output_layer.get_weights()[1])):
        img_loss: Optional[Tuple[np.ndarray, float]] = _generate_filter_image(input_img,
                                                                              output_layer.output,
                                                                              f)
        if img_loss is not None:
            processed_filters.append(img_loss)

    print('{} filter processed.'.format(len(processed_filters)))
    # Finally draw and store the best filters to disk
    _draw_filters(processed_filters)

if __name__ == "__main__":
    # the name of the layer we want to visualize
    # (see model definition at keras/applications/vgg16.py)
    LAYER_NAME = 'block5_conv1'

    # build the VGG16 network with ImageNet weights
    vgg = vgg16.VGG16(weights='imagenet', include_top=False)
    print('Model loaded.')
    print(vgg.summary())

    # example function call
    visualize_layer(vgg, LAYER_NAME)
