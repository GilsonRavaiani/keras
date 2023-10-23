from keras import backend
from keras import constraints
from keras import initializers
from keras import ops
from keras import regularizers
from keras.api_export import keras_export
from keras.backend import standardize_dtype
from keras.layers.input_spec import InputSpec
from keras.layers.layer import Layer


@keras_export("keras.layers.BatchNormalization")
class BatchNormalization(Layer):
    """Layer that normalizes its inputs.

    Batch normalization applies a transformation that maintains the mean output
    close to 0 and the output standard deviation close to 1.

    Importantly, batch normalization works differently during training and
    during inference.

    **During training** (i.e. when using `fit()` or when calling the layer/model
    with the argument `training=True`), the layer normalizes its output using
    the mean and standard deviation of the current batch of inputs. That is to
    say, for each channel being normalized, the layer returns
    `gamma * (batch - mean(batch)) / sqrt(var(batch) + epsilon) + beta`, where:

    - `epsilon` is small constant (configurable as part of the constructor
    arguments)
    - `gamma` is a learned scaling factor (initialized as 1), which
    can be disabled by passing `scale=False` to the constructor.
    - `beta` is a learned offset factor (initialized as 0), which
    can be disabled by passing `center=False` to the constructor.

    **During inference** (i.e. when using `evaluate()` or `predict()` or when
    calling the layer/model with the argument `training=False` (which is the
    default), the layer normalizes its output using a moving average of the
    mean and standard deviation of the batches it has seen during training. That
    is to say, it returns
    `gamma * (batch - self.moving_mean) / sqrt(self.moving_var+epsilon) + beta`.

    `self.moving_mean` and `self.moving_var` are non-trainable variables that
    are updated each time the layer in called in training mode, as such:

    - `moving_mean = moving_mean * momentum + mean(batch) * (1 - momentum)`
    - `moving_var = moving_var * momentum + var(batch) * (1 - momentum)`

    As such, the layer will only normalize its inputs during inference
    *after having been trained on data that has similar statistics as the
    inference data*.

    Args:
        axis: Integer, the axis that should be normalized
            (typically the features axis). For instance, after a `Conv2D` layer
            with `data_format="channels_first"`, use `axis=1`.
        momentum: Momentum for the moving average.
        epsilon: Small float added to variance to avoid dividing by zero.
        center: If `True`, add offset of `beta` to normalized tensor.
            If `False`, `beta` is ignored.
        scale: If `True`, multiply by `gamma`. If `False`, `gamma` is not used.
            When the next layer is linear this can be disabled
            since the scaling will be done by the next layer.
        beta_initializer: Initializer for the beta weight.
        gamma_initializer: Initializer for the gamma weight.
        moving_mean_initializer: Initializer for the moving mean.
        moving_variance_initializer: Initializer for the moving variance.
        beta_regularizer: Optional regularizer for the beta weight.
        gamma_regularizer: Optional regularizer for the gamma weight.
        beta_constraint: Optional constraint for the beta weight.
        gamma_constraint: Optional constraint for the gamma weight.
        synchronized: If `True`, synchronizes the global batch statistics (mean and
            variance) for the layer across all devices at each training step in a
            distributed training strategy. If `False`, each replica uses its own
            local batch statistics.
        **kwargs: Base layer keyword arguments (e.g. `name` and `dtype`).

    Call arguments:
        inputs: Input tensor (of any rank).
        training: Python boolean indicating whether the layer should behave in
            training mode or in inference mode.
            - `training=True`: The layer will normalize its inputs using
            the mean and variance of the current batch of inputs.
            - `training=False`: The layer will normalize its inputs using
            the mean and variance of its moving statistics, learned during
            training.

    Reference:

    - [Ioffe and Szegedy, 2015](https://arxiv.org/abs/1502.03167).

    **About setting `layer.trainable = False` on a `BatchNormalization` layer:**

    The meaning of setting `layer.trainable = False` is to freeze the layer,
    i.e. its internal state will not change during training:
    its trainable weights will not be updated
    during `fit()` or `train_on_batch()`, and its state updates will not be run.

    Usually, this does not necessarily mean that the layer is run in inference
    mode (which is normally controlled by the `training` argument that can
    be passed when calling a layer). "Frozen state" and "inference mode"
    are two separate concepts.

    However, in the case of the `BatchNormalization` layer, **setting
    `trainable = False` on the layer means that the layer will be
    subsequently run in inference mode** (meaning that it will use
    the moving mean and the moving variance to normalize the current batch,
    rather than using the mean and variance of the current batch).

    Note that:

    - Setting `trainable` on an model containing other layers will recursively
        set the `trainable` value of all inner layers.
    - If the value of the `trainable` attribute is changed after calling
        `compile()` on a model, the new value doesn't take effect for this model
        until `compile()` is called again.
    """

    def __init__(
        self,
        axis=-1,
        momentum=0.99,
        epsilon=1e-3,
        center=True,
        scale=True,
        beta_initializer="zeros",
        gamma_initializer="ones",
        moving_mean_initializer="zeros",
        moving_variance_initializer="ones",
        beta_regularizer=None,
        gamma_regularizer=None,
        beta_constraint=None,
        gamma_constraint=None,
        synchronized=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.axis = int(axis)

        if synchronized and backend.backend() != "tensorflow":
            raise ValueError("Argument synchronized=True is only supported with the TensorFlow backend.")

        self.synchronized = synchronized

        self.momentum = float(momentum)
        self.epsilon = float(epsilon)
        self.center = center
        self.scale = scale
        self.beta_initializer = initializers.get(beta_initializer)
        self.gamma_initializer = initializers.get(gamma_initializer)
        self.moving_mean_initializer = initializers.get(moving_mean_initializer)
        self.moving_variance_initializer = initializers.get(
            moving_variance_initializer
        )
        self.beta_regularizer = regularizers.get(beta_regularizer)
        self.gamma_regularizer = regularizers.get(gamma_regularizer)
        self.beta_constraint = constraints.get(beta_constraint)
        self.gamma_constraint = constraints.get(gamma_constraint)
        self.supports_masking = True

    def build(self, input_shape):
        shape = (input_shape[self.axis],)
        if self.scale:
            self.gamma = self.add_weight(
                shape=shape,
                name="gamma",
                initializer=self.gamma_initializer,
                regularizer=self.gamma_regularizer,
                constraint=self.gamma_constraint,
                trainable=True,
            )
        if self.center:
            self.beta = self.add_weight(
                shape=shape,
                name="beta",
                initializer=self.beta_initializer,
                regularizer=self.beta_regularizer,
                constraint=self.beta_constraint,
                trainable=True,
            )
        self.moving_mean = self.add_weight(
            shape=shape,
            name="moving_mean",
            initializer=self.moving_mean_initializer,
            trainable=False,
        )
        self.moving_variance = self.add_weight(
            shape=shape,
            name="moving_variance",
            initializer=self.moving_variance_initializer,
            trainable=False,
        )
        self.input_spec = InputSpec(
            ndim=len(input_shape), axes={self.axis: input_shape[self.axis]}
        )
        reduction_axes = list(range(len(input_shape)))
        del reduction_axes[self.axis]
        self._reduction_axes = reduction_axes
        self.built = True

    def compute_output_shape(self, input_shape):
        return input_shape
    

    def calculate_mean_and_var(self, inputs):

        if not self.synchronized:
            return ops.moments(
                inputs, axes=self._reduction_axes, keepdims=True
            )

        axes = self._reduction_axes
        y = inputs

        if backend() == "tensorflow":
            
            from keras.utils.module_utils import tensorflow as tf
            replica_ctx = tf.distribute.get_replica_context()

            if replica_ctx:
                local_sum = ops.sum(y, axis=axes, keepdims=True)
                local_squared_sum = ops.sum(ops.square(y), axis=axes, keepdims=True)
                batch_size = ops.cast(ops.shape(y)[axes[0]], dtype="float32")

                y_sum = replica_ctx.all_reduce(tf.distribute.ReduceOp.SUM, local_sum)
                y_squared_sum = replica_ctx.all_reduce(tf.distribute.ReduceOp.SUM, local_squared_sum)
                global_batch_size = replica_ctx.all_reduce(tf.distribute.ReduceOp.SUM, batch_size)

                axes_vals = [(ops.shape(y))[axes[i]] for i in range(1, len(axes))]
                multiplier = ops.cast(ops.prod(axes_vals), "float32")
                multiplier = multiplier * global_batch_size

                mean = y_sum / multiplier
                y_squared_mean = y_squared_sum / multiplier
                # var = E(x^2) - E(x)^2
                variance = y_squared_mean - ops.square(mean)
            else:
                # Compute true mean while keeping the dims for proper broadcasting.
                mean = ops.mean(y, axes, keepdims=True, name="mean")
                # sample variance, not unbiased variance
                # Note: stop_gradient does not change the gradient that gets
                #       backpropagated to the mean from the variance calculation,
                #       because that gradient is zero
                variance = ops.reduce_mean(
                    tf.math.squared_difference(y, ops.stop_gradient(mean)), axes, keepdims=True, name="variance"
                )

            mean = ops.cast(mean, inputs.dtype)
            variance = ops.cast(variance, inputs.dtype)
                
            return (mean, variance)
        elif backend() == "jax":
            raise NotImplementedError
        elif backend() == "torch":
            raise NotImplementedError


    def call(self, inputs, training=None, mask=None):
        input_dtype = standardize_dtype(inputs.dtype)
        if input_dtype in ("float16", "bfloat16"):
            # BN is prone to overflowing for float16/bfloat16 inputs, so we opt
            # out BN for mixed precision.
            inputs = ops.cast(inputs, "float32")

        broadcast_shape = [1] * len(inputs.shape)
        broadcast_shape[self.axis] = inputs.shape[self.axis]
        if training and self.trainable:
            mean, variance = self.calculate_mean_and_var(inputs)
            moving_mean = ops.cast(self.moving_mean, inputs.dtype)
            moving_variance = ops.cast(self.moving_variance, inputs.dtype)
            self.moving_mean.assign(
                ops.cast(
                    moving_mean * self.momentum
                    + ops.squeeze(mean, self._reduction_axes)
                    * (1.0 - self.momentum),
                    inputs.dtype,
                )
            )
            self.moving_variance.assign(
                ops.cast(
                    moving_variance * self.momentum
                    + ops.squeeze(variance, self._reduction_axes)
                    * (1.0 - self.momentum),
                    inputs.dtype,
                )
            )
        else:
            moving_mean = ops.cast(self.moving_mean, inputs.dtype)
            moving_variance = ops.cast(self.moving_variance, inputs.dtype)
            moving_mean = ops.reshape(moving_mean, broadcast_shape)
            moving_variance = ops.reshape(moving_variance, broadcast_shape)
            mean = moving_mean
            variance = moving_variance

        inv = ops.rsqrt(variance + self.epsilon)
        if self.scale:
            gamma = ops.reshape(self.gamma, broadcast_shape)
            gamma = ops.cast(gamma, inputs.dtype)
            inv = inv * gamma

        res = -mean * inv
        if self.center:
            beta = ops.reshape(self.beta, broadcast_shape)
            beta = ops.cast(beta, inputs.dtype)
            res = res + beta

        # Note: Folding BatchNormalization depends on the precise order of ops
        # that are generated by the expression below
        outputs = inputs * inv + res
        return ops.cast(outputs, input_dtype)

    def get_config(self):
        base_config = super().get_config()
        config = {
            "axis": self.axis,
            "momentum": self.momentum,
            "epsilon": self.epsilon,
            "center": self.center,
            "scale": self.scale,
            "beta_initializer": initializers.serialize(self.beta_initializer),
            "gamma_initializer": initializers.serialize(self.gamma_initializer),
            "moving_mean_initializer": initializers.serialize(
                self.moving_mean_initializer
            ),
            "moving_variance_initializer": initializers.serialize(
                self.moving_variance_initializer
            ),
            "beta_regularizer": regularizers.serialize(self.beta_regularizer),
            "gamma_regularizer": regularizers.serialize(self.gamma_regularizer),
            "beta_constraint": constraints.serialize(self.beta_constraint),
            "gamma_constraint": constraints.serialize(self.gamma_constraint),
        }
        return {**base_config, **config}
