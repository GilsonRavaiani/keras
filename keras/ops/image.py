import warnings

from keras import backend
from keras.api_export import keras_export
from keras.backend import KerasTensor
from keras.backend import any_symbolic_tensors
from keras.ops.operation import Operation
from keras.ops.operation_utils import compute_conv_output_shape


class Resize(Operation):
    def __init__(
        self,
        size,
        interpolation="bilinear",
        antialias=False,
        data_format="channels_last",
    ):
        super().__init__()
        self.size = tuple(size)
        self.interpolation = interpolation
        self.antialias = antialias
        self.data_format = data_format

    def call(self, image):
        return backend.image.resize(
            image,
            self.size,
            interpolation=self.interpolation,
            antialias=self.antialias,
            data_format=self.data_format,
        )

    def compute_output_spec(self, image):
        if len(image.shape) == 3:
            return KerasTensor(
                self.size + (image.shape[-1],), dtype=image.dtype
            )
        elif len(image.shape) == 4:
            if self.data_format == "channels_last":
                return KerasTensor(
                    (image.shape[0],) + self.size + (image.shape[-1],),
                    dtype=image.dtype,
                )
            else:
                return KerasTensor(
                    (image.shape[0], image.shape[1]) + self.size,
                    dtype=image.dtype,
                )
        raise ValueError(
            "Invalid input rank: expected rank 3 (single image) "
            "or rank 4 (batch of images). Received input with shape: "
            f"image.shape={image.shape}"
        )


@keras_export("keras.ops.image.resize")
def resize(
    image,
    size,
    interpolation="bilinear",
    antialias=False,
    data_format="channels_last",
):
    """Resize images to size using the specified interpolation method.

    Args:
        image: Input image or batch of images. Must be 3D or 4D.
        size: Size of output image in `(height, width)` format.
        interpolation: Interpolation method. Available methods are `"nearest"`,
            `"bilinear"`, and `"bicubic"`. Defaults to `"bilinear"`.
        antialias: Whether to use an antialiasing filter when downsampling an
            image. Defaults to `False`.
        data_format: string, either `"channels_last"` or `"channels_first"`.
            The ordering of the dimensions in the inputs. `"channels_last"`
            corresponds to inputs with shape `(batch, height, width, channels)`
            while `"channels_first"` corresponds to inputs with shape
            `(batch, channels, height, weight)`. It defaults to the
            `image_data_format` value found in your Keras config file at
            `~/.keras/keras.json`. If you never set it, then it will be
            `"channels_last"`.

    Returns:
        Resized image or batch of images.

    Examples:

    >>> x = np.random.random((2, 4, 4, 3)) # batch of 2 RGB images
    >>> y = keras.ops.image.resize(x, (2, 2))
    >>> y.shape
    (2, 2, 2, 3)

    >>> x = np.random.random((4, 4, 3)) # single RGB image
    >>> y = keras.ops.image.resize(x, (2, 2))
    >>> y.shape
    (2, 2, 3)

    >>> x = np.random.random((2, 3, 4, 4)) # batch of 2 RGB images
    >>> y = keras.ops.image.resize(x, (2, 2),
    ...     data_format="channels_first")
    >>> y.shape
    (2, 3, 2, 2)
    """

    if any_symbolic_tensors((image,)):
        return Resize(
            size,
            interpolation=interpolation,
            antialias=antialias,
            data_format=data_format,
        ).symbolic_call(image)
    return backend.image.resize(
        image,
        size,
        interpolation=interpolation,
        antialias=antialias,
        data_format=data_format,
    )


class AffineTransform(Operation):
    def __init__(
        self,
        interpolation="bilinear",
        fill_mode="constant",
        fill_value=0,
        data_format="channels_last",
    ):
        super().__init__()
        self.interpolation = interpolation
        self.fill_mode = fill_mode
        self.fill_value = fill_value
        self.data_format = data_format

    def call(self, image, transform):
        return backend.image.affine_transform(
            image,
            transform,
            interpolation=self.interpolation,
            fill_mode=self.fill_mode,
            fill_value=self.fill_value,
            data_format=self.data_format,
        )

    def compute_output_spec(self, image, transform):
        if len(image.shape) not in (3, 4):
            raise ValueError(
                "Invalid image rank: expected rank 3 (single image) "
                "or rank 4 (batch of images). Received input with shape: "
                f"image.shape={image.shape}"
            )
        if len(transform.shape) not in (1, 2):
            raise ValueError(
                "Invalid transform rank: expected rank 1 (single transform) "
                "or rank 2 (batch of transforms). Received input with shape: "
                f"transform.shape={transform.shape}"
            )
        return KerasTensor(image.shape, dtype=image.dtype)


@keras_export("keras.ops.image.affine_transform")
def affine_transform(
    image,
    transform,
    interpolation="bilinear",
    fill_mode="constant",
    fill_value=0,
    data_format="channels_last",
):
    """Applies the given transform(s) to the image(s).

    Args:
        image: Input image or batch of images. Must be 3D or 4D.
        transform: Projective transform matrix/matrices. A vector of length 8 or
            tensor of size N x 8. If one row of transform is
            `[a0, a1, a2, b0, b1, b2, c0, c1]`, then it maps the output point
            `(x, y)` to a transformed input point
            `(x', y') = ((a0 x + a1 y + a2) / k, (b0 x + b1 y + b2) / k)`,
            where `k = c0 x + c1 y + 1`. The transform is inverted compared to
            the transform mapping input points to output points. Note that
            gradients are not backpropagated into transformation parameters.
            Note that `c0` and `c1` are only effective when using TensorFlow
            backend and will be considered as `0` when using other backends.
        interpolation: Interpolation method. Available methods are `"nearest"`,
            and `"bilinear"`. Defaults to `"bilinear"`.
        fill_mode: Points outside the boundaries of the input are filled
            according to the given mode. Available methods are `"constant"`,
            `"nearest"`, `"wrap"` and `"reflect"`. Defaults to `"constant"`.
            - `"reflect"`: `(d c b a | a b c d | d c b a)`
                The input is extended by reflecting about the edge of the last
                pixel.
            - `"constant"`: `(k k k k | a b c d | k k k k)`
                The input is extended by filling all values beyond
                the edge with the same constant value k specified by
                `fill_value`.
            - `"wrap"`: `(a b c d | a b c d | a b c d)`
                The input is extended by wrapping around to the opposite edge.
            - `"nearest"`: `(a a a a | a b c d | d d d d)`
                The input is extended by the nearest pixel.
        fill_value: Value used for points outside the boundaries of the input if
            `fill_mode="constant"`. Defaults to `0`.
        data_format: string, either `"channels_last"` or `"channels_first"`.
            The ordering of the dimensions in the inputs. `"channels_last"`
            corresponds to inputs with shape `(batch, height, width, channels)`
            while `"channels_first"` corresponds to inputs with shape
            `(batch, channels, height, weight)`. It defaults to the
            `image_data_format` value found in your Keras config file at
            `~/.keras/keras.json`. If you never set it, then it will be
            `"channels_last"`.

    Returns:
        Applied affine transform image or batch of images.

    Examples:

    >>> x = np.random.random((2, 64, 80, 3)) # batch of 2 RGB images
    >>> transform = np.array(
    ...     [
    ...         [1.5, 0, -20, 0, 1.5, -16, 0, 0],  # zoom
    ...         [1, 0, -20, 0, 1, -16, 0, 0],  # translation
    ...     ]
    ... )
    >>> y = keras.ops.image.affine_transform(x, transform)
    >>> y.shape
    (2, 64, 80, 3)

    >>> x = np.random.random((64, 80, 3)) # single RGB image
    >>> transform = np.array([1.0, 0.5, -20, 0.5, 1.0, -16, 0, 0])  # shear
    >>> y = keras.ops.image.affine_transform(x, transform)
    >>> y.shape
    (64, 80, 3)

    >>> x = np.random.random((2, 3, 64, 80)) # batch of 2 RGB images
    >>> transform = np.array(
    ...     [
    ...         [1.5, 0, -20, 0, 1.5, -16, 0, 0],  # zoom
    ...         [1, 0, -20, 0, 1, -16, 0, 0],  # translation
    ...     ]
    ... )
    >>> y = keras.ops.image.affine_transform(x, transform,
    ...     data_format="channels_first")
    >>> y.shape
    (2, 3, 64, 80)
    """
    if any_symbolic_tensors((image, transform)):
        return AffineTransform(
            interpolation=interpolation,
            fill_mode=fill_mode,
            fill_value=fill_value,
            data_format=data_format,
        ).symbolic_call(image, transform)
    return backend.image.affine_transform(
        image,
        transform,
        interpolation=interpolation,
        fill_mode=fill_mode,
        fill_value=fill_value,
        data_format=data_format,
    )


class ExtractPatches(Operation):
    def __init__(
        self,
        size,
        strides=None,
        dilation_rate=1,
        padding="valid",
        data_format="channels_last",
    ):
        super().__init__()
        if isinstance(size, int):
            size = (size, size)
        self.size = size
        self.strides = strides
        self.dilation_rate = dilation_rate
        self.padding = padding
        self.data_format = data_format

    def call(self, image):
        return _extract_patches(
            image=image,
            size=self.size,
            strides=self.strides,
            dilation_rate=self.dilation_rate,
            padding=self.padding,
            data_format=self.data_format,
        )

    def compute_output_spec(self, image):
        image_shape = image.shape
        if not self.strides:
            strides = (self.size[0], self.size[1])
        if self.data_format == "channels_last":
            channels_in = image.shape[-1]
        else:
            channels_in = image.shape[-3]
        if len(image.shape) == 3:
            image_shape = (1,) + image_shape
        filters = self.size[0] * self.size[1] * channels_in
        kernel_size = (self.size[0], self.size[1])
        out_shape = compute_conv_output_shape(
            image_shape,
            filters,
            kernel_size,
            strides=strides,
            padding=self.padding,
            data_format=self.data_format,
            dilation_rate=self.dilation_rate,
        )
        if len(image.shape) == 3:
            out_shape = out_shape[1:]
        return KerasTensor(shape=out_shape, dtype=image.dtype)


@keras_export("keras.ops.image.extract_patches")
def extract_patches(
    image,
    size,
    strides=None,
    dilation_rate=1,
    padding="valid",
    data_format="channels_last",
):
    """Extracts patches from the image(s).

    Args:
        image: Input image or batch of images. Must be 3D or 4D.
        size: Patch size int or tuple (patch_height, patch_widht)
        strides: strides along height and width. If not specified, or
            if `None`, it defaults to the same value as `size`.
        dilation_rate: This is the input stride, specifying how far two
            consecutive patch samples are in the input. For value other than 1,
            strides must be 1. NOTE: `strides > 1` is not supported in
            conjunction with `dilation_rate > 1`
        padding: The type of padding algorithm to use: `"same"` or `"valid"`.
        data_format: string, either `"channels_last"` or `"channels_first"`.
            The ordering of the dimensions in the inputs. `"channels_last"`
            corresponds to inputs with shape `(batch, height, width, channels)`
            while `"channels_first"` corresponds to inputs with shape
            `(batch, channels, height, weight)`. It defaults to the
            `image_data_format` value found in your Keras config file at
            `~/.keras/keras.json`. If you never set it, then it will be
            `"channels_last"`.

    Returns:
        Extracted patches 3D (if not batched) or 4D (if batched)

    Examples:

    >>> image = np.random.random(
    ...     (2, 20, 20, 3)
    ... ).astype("float32") # batch of 2 RGB images
    >>> patches = keras.ops.image.extract_patches(image, (5, 5))
    >>> patches.shape
    (2, 4, 4, 75)
    >>> image = np.random.random((20, 20, 3)).astype("float32") # 1 RGB image
    >>> patches = keras.ops.image.extract_patches(image, (3, 3), (1, 1))
    >>> patches.shape
    (18, 18, 27)
    """
    if any_symbolic_tensors((image,)):
        return ExtractPatches(
            size=size,
            strides=strides,
            dilation_rate=dilation_rate,
            padding=padding,
            data_format=data_format,
        ).symbolic_call(image)

    return _extract_patches(
        image, size, strides, dilation_rate, padding, data_format=data_format
    )


def _extract_patches(
    image,
    size,
    strides=None,
    dilation_rate=1,
    padding="valid",
    data_format="channels_last",
):
    if isinstance(size, int):
        patch_h = patch_w = size
    elif len(size) == 2:
        patch_h, patch_w = size[0], size[1]
    else:
        raise TypeError(
            "Invalid `size` argument. Expected an "
            f"int or a tuple of length 2. Received: size={size}"
        )
    if data_format == "channels_last":
        channels_in = image.shape[-1]
    elif data_format == "channels_first":
        channels_in = image.shape[-3]
    if not strides:
        strides = size
    out_dim = patch_h * patch_w * channels_in
    kernel = backend.numpy.eye(out_dim)
    kernel = backend.numpy.reshape(
        kernel, (patch_h, patch_w, channels_in, out_dim)
    )
    _unbatched = False
    if len(image.shape) == 3:
        _unbatched = True
        image = backend.numpy.expand_dims(image, axis=0)
    patches = backend.nn.conv(
        inputs=image,
        kernel=kernel,
        strides=strides,
        padding=padding,
        data_format=data_format,
        dilation_rate=dilation_rate,
    )
    if _unbatched:
        patches = backend.numpy.squeeze(patches, axis=0)
    return patches


class MapCoordinates(Operation):
    def __init__(self, order, fill_mode="constant", fill_value=0):
        super().__init__()
        self.order = order
        self.fill_mode = fill_mode
        self.fill_value = fill_value

    def call(self, image, coordinates):
        return backend.image.map_coordinates(
            image,
            coordinates,
            order=self.order,
            fill_mode=self.fill_mode,
            fill_value=self.fill_value,
        )

    def compute_output_spec(self, image, coordinates):
        if coordinates.shape[0] != len(image.shape):
            raise ValueError(
                "First dim of `coordinates` must be the same as the rank of "
                "`image`. "
                f"Received image with shape: {image.shape} and coordinate "
                f"leading dim of {coordinates.shape[0]}"
            )
        if len(coordinates.shape) < 2:
            raise ValueError(
                "Invalid coordinates rank: expected at least rank 2."
                f" Received input with shape: {coordinates.shape}"
            )
        return KerasTensor(coordinates.shape[1:], dtype=image.dtype)


@keras_export("keras.ops.image.map_coordinates")
def map_coordinates(
    input, coordinates, order, fill_mode="constant", fill_value=0
):
    """Map the input array to new coordinates by interpolation..

    Note that interpolation near boundaries differs from the scipy function,
    because we fixed an outstanding bug
    [scipy/issues/2640](https://github.com/scipy/scipy/issues/2640).

    Args:
        input: The input array.
        coordinates: The coordinates at which input is evaluated.
        order: The order of the spline interpolation. The order must be `0` or
            `1`. `0` indicates the nearest neighbor and `1` indicates the linear
            interpolation.
        fill_mode: Points outside the boundaries of the input are filled
            according to the given mode. Available methods are `"constant"`,
            `"nearest"`, `"wrap"` and `"mirror"` and `"reflect"`. Defaults to
            `"constant"`.
            - `"constant"`: `(k k k k | a b c d | k k k k)`
                The input is extended by filling all values beyond
                the edge with the same constant value k specified by
                `fill_value`.
            - `"nearest"`: `(a a a a | a b c d | d d d d)`
                The input is extended by the nearest pixel.
            - `"wrap"`: `(a b c d | a b c d | a b c d)`
                The input is extended by wrapping around to the opposite edge.
            - `"mirror"`: `(c d c b | a b c d | c b a b)`
                The input is extended by mirroring about the edge.
            - `"reflect"`: `(d c b a | a b c d | d c b a)`
                The input is extended by reflecting about the edge of the last
                pixel.
        fill_value: Value used for points outside the boundaries of the input if
            `fill_mode="constant"`. Defaults to `0`.

    Returns:
        Output image or batch of images.

    """
    if any_symbolic_tensors((input, coordinates)):
        return MapCoordinates(
            order,
            fill_mode,
            fill_value,
        ).symbolic_call(input, coordinates)
    return backend.image.map_coordinates(
        input,
        coordinates,
        order,
        fill_mode,
        fill_value,
    )


class PadImages(Operation):
    def __init__(
        self,
        top_padding,
        bottom_padding,
        left_padding,
        right_padding,
        target_height,
        target_width,
    ):
        super().__init__()
        self.top_padding = top_padding
        self.bottom_padding = bottom_padding
        self.left_padding = left_padding
        self.right_padding = right_padding
        self.target_height = target_height
        self.target_width = target_width

    def call(self, image):
        return _pad_images(
            image,
            self.top_padding,
            self.bottom_padding,
            self.left_padding,
            self.right_padding,
            self.target_height,
            self.target_width,
        )

    def compute_output_spec(self, image):
        if self.target_height is None:
            height_axis = 0 if len(image.shape) == 3 else 1
            self.target_height = (
                self.top_padding
                + image.shape[height_axis]
                + self.bottom_padding
            )
        if self.target_width is None:
            width_axis = 0 if len(image.shape) == 3 else 2
            self.target_width = (
                self.left_padding + image.shape[width_axis] + self.right_padding
            )
        out_shape = (
            image.shape[0],
            self.target_height,
            self.target_width,
            image.shape[-1],
        )
        if len(image.shape) == 3:
            out_shape = out_shape[1:]
        return KerasTensor(
            shape=out_shape,
            dtype=image.dtype,
        )


def _pad_images(
    image,
    top_padding,
    bottom_padding,
    left_padding,
    right_padding,
    target_height,
    target_width,
):
    image = backend.convert_to_tensor(image)
    is_batch = True
    image_shape = image.shape
    if len(image_shape) == 3:
        is_batch = False
        image = backend.numpy.expand_dims(image, 0)
    elif len(image_shape) != 4:
        raise ValueError(
            f"'image' (shape {image_shape}) must have either 3 or 4 dimensions."
        )

    batch, height, width, depth = image.shape

    if right_padding is None and target_width is None:
        raise ValueError("right_padding and target_width both cannot be None.")
    if right_padding is not None and target_width is not None:
        right_padding = None
        warnings.warn(
            "Both right_padding and target_width were provided. "
            "Setting right_padding to None. target_width will be "
            "used for calculating right_padding."
        )
    if right_padding is None:
        right_padding = target_width - left_padding - width

    if bottom_padding is None and target_height is None:
        raise ValueError(
            "bottom_padding and target_height both cannot " "be None."
        )
    if bottom_padding is not None and target_height is not None:
        bottom_padding = None
        warnings.warn(
            "Both bottom_padding and target_height were provided. "
            "Setting bottom_padding to None. target_height will be "
            "used for calculating bottom_padding."
        )
    if bottom_padding is None:
        bottom_padding = target_height - top_padding - height

    if not top_padding >= 0:
        raise ValueError("top_padding must be >= 0")
    if not left_padding >= 0:
        raise ValueError("left_padding must be >= 0")
    if not right_padding >= 0:
        raise ValueError("width must be <= target - offset")
    if not bottom_padding >= 0:
        raise ValueError("height must be <= target - offset")

    paddings = backend.numpy.reshape(
        backend.numpy.stack(
            [
                0,
                0,
                top_padding,
                bottom_padding,
                left_padding,
                right_padding,
                0,
                0,
            ]
        ),
        [4, 2],
    )
    padded = backend.numpy.pad(image, paddings)

    if target_height is None:
        target_height = top_padding + height + bottom_padding
    if target_width is None:
        target_width = left_padding + width + right_padding
    padded_shape = [batch, target_height, target_width, depth]
    padded = backend.numpy.reshape(padded, padded_shape)

    if not is_batch:
        padded = backend.numpy.squeeze(padded, axis=[0])
    return padded


@keras_export("keras.ops.image.pad_images")
def pad_images(
    image,
    top_padding,
    left_padding,
    target_height,
    target_width,
    bottom_padding=None,
    right_padding=None,
):
    """Pad `image` with zeros to the specified `height` and `width`.

    Args:
        image: 4-D Tensor of shape `(batch, height, width, channels)` or 3-D
            Tensor of shape `(height, width, channels)`.
        top_padding: Number of rows of zeros to add on top.
        bottom_padding: Number of rows of zeros to add at the bottom.
        left_padding: Number of columns of zeros to add on the left.
        right_padding: Number of columns of zeros to add on the right.
        target_height: Height of output image.
        target_width: Width of output image.

    Returns:
        If `image` was 4-D, a 4-D float Tensor of shape
            `(batch, target_height, target_width, channels)`
        If `image` was 3-D, a 3-D float Tensor of shape
            `(target_height, target_width, channels)`

    Example:

    >>> image = np.random.random((15, 25, 3))
    >>> padded_image = keras.ops.image.pad_images(
    ...     image, 2, 3, target_height=20, target_width=30
    ... )
    >>> padded_image.shape
    (20, 30, 3)

    >>> batch_images = np.random.random((2, 15, 25, 3))
    >>> padded_batch = keras.ops.image.pad_images(
    ...     batch_images, 2, 3, target_height=20, target_width=30
    ... )
    >>> padded_batch.shape
    (2, 20, 30, 3)"""

    if any_symbolic_tensors((image,)):
        return PadImage(
            top_padding,
            bottom_padding,
            left_padding,
            right_padding,
            target_height,
            target_width,
        ).symbolic_call(image)

    return _pad_images(
        image,
        top_padding,
        bottom_padding,
        left_padding,
        right_padding,
        target_height,
        target_width,
    )
