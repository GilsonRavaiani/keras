# -*- coding: utf-8 -*-
from __future__ import absolute_import
import numpy as np

from .. import backend as K
from .. import activations, initializations, regularizers
from ..engine import Layer, InputSpec


def time_distributed_dense(x, w, b=None, dropout=None,
                           input_dim=None, output_dim=None, timesteps=None):
    '''Apply y.w + b for every temporal slice y of x.
    '''
    if not input_dim:
        # won't work with TensorFlow
        input_dim = K.shape(x)[2]
    if not timesteps:
        # won't work with TensorFlow
        timesteps = K.shape(x)[1]
    if not output_dim:
        # won't work with TensorFlow
        output_dim = K.shape(w)[1]

    if dropout is not None and 0. < dropout < 1.:
        # apply the same dropout pattern at every timestep
        ones = K.ones_like(K.reshape(x[:, 0, :], (-1, input_dim)))
        dropout_matrix = K.dropout(ones, dropout)
        expanded_dropout_matrix = K.repeat(dropout_matrix, timesteps)
        x = K.in_train_phase(x * expanded_dropout_matrix, x)

    # collapse time dimension and batch dimension together
    x = K.reshape(x, (-1, input_dim))

    x = K.dot(x, w)
    if b:
        x = x + b
    # reshape to 3D tensor
    x = K.reshape(x, (-1, timesteps, output_dim))
    return x


class Recurrent(Layer):
    '''Abstract base class for recurrent layers.
    Do not use in a model -- it's not a valid layer!
    Use its children classes `LSTM`, `GRU` and `SimpleRNN` instead.

    All recurrent layers (`LSTM`, `GRU`, `SimpleRNN`) also
    follow the specifications of this class and accept
    the keyword arguments listed below.

    # Example

    ```python
        # as the first layer in a Sequential model
        model = Sequential()
        model.add(LSTM(32, input_shape=(10, 64)))
        # now model.output_shape == (None, 10, 32)
        # note: `None` is the batch dimension.

        # the following is identical:
        model = Sequential()
        model.add(LSTM(32, input_dim=64, input_length=10))

        # for subsequent layers, not need to specify the input size:
        model.add(LSTM(16))
    ```

    # Arguments
        weights: list of Numpy arrays to set as initial weights.
            The list should have 3 elements, of shapes:
            `[(input_dim, output_dim), (output_dim, output_dim), (output_dim,)]`.
        return_sequences: Boolean. Whether to return the last output
            in the output sequence, or the full sequence.
        go_backwards: Boolean (default False).
            If True, process the input sequence backwards.
        stateful: Boolean (default False). If True, the last state
            for each sample at index i in a batch will be used as initial
            state for the sample of index i in the following batch.
        unroll: Boolean (default False). If True, the network will be unrolled,
            else a symbolic loop will be used. When using TensorFlow, the network
            is always unrolled, so this argument does not do anything.
            Unrolling can speed-up a RNN, although it tends to be more memory-intensive.
            Unrolling is only suitable for short sequences.
        consume_less: one of "cpu", "mem", or "gpu" (LSTM/GRU only).
            If set to "cpu", the RNN will use
            an implementation that uses fewer, larger matrix products,
            thus running faster on CPU but consuming more memory.
            If set to "mem", the RNN will use more matrix products,
            but smaller ones, thus running slower (may actually be faster on GPU)
            while consuming less memory.
            If set to "gpu" (LSTM/GRU only), the RNN will combine the input gate,
            the forget gate and the output gate into a single matrix,
            enabling more time-efficient parallelization on the GPU. Note: RNN
            dropout must be shared for all gates, resulting in a slightly
            reduced regularization.
        input_dim: dimensionality of the input (integer).
            This argument (or alternatively, the keyword argument `input_shape`)
            is required when using this layer as the first layer in a model.
        input_length: Length of input sequences, to be specified
            when it is constant.
            This argument is required if you are going to connect
            `Flatten` then `Dense` layers upstream
            (without it, the shape of the dense outputs cannot be computed).
            Note that if the recurrent layer is not the first layer
            in your model, you would need to specify the input length
            at the level of the first layer
            (e.g. via the `input_shape` argument)
        batch_norm: Boolean (default False). If True, use batch normalization,
            which could be slow when using cpu.
        batch_norm_gamma: gamma initialization parameter when using batch normalization.

    # Input shape
        3D tensor with shape `(nb_samples, timesteps, input_dim)`.

    # Output shape
        - if `return_sequences`: 3D tensor with shape
            `(nb_samples, timesteps, output_dim)`.
        - else, 2D tensor with shape `(nb_samples, output_dim)`.

    # Masking
        This layer supports masking for input data with a variable number
        of timesteps. To introduce masks to your data,
        use an [Embedding](embeddings.md) layer with the `mask_zero` parameter
        set to `True`.

    # TensorFlow warning
        For the time being, when using the TensorFlow backend,
        the number of timesteps used must be specified in your model.
        Make sure to pass an `input_length` int argument to your
        recurrent layer (if it comes first in your model),
        or to pass a complete `input_shape` argument to the first layer
        in your model otherwise.

    # Note on using statefulness in RNNs
        You can set RNN layers to be 'stateful', which means that the states
        computed for the samples in one batch will be reused as initial states
        for the samples in the next batch.
        This assumes a one-to-one mapping between
        samples in different successive batches.

        To enable statefulness:
            - specify `stateful=True` in the layer constructor.
            - specify a fixed batch size for your model, by passing
                a `batch_input_shape=(...)` to the first layer in your model.
                This is the expected shape of your inputs *including the batch size*.
                It should be a tuple of integers, e.g. `(32, 10, 100)`.

        To reset the states of your model, call `.reset_states()` on either
        a specific layer, or on your entire model.

    # Note on using dropout with TensorFlow
        When using the TensorFlow backend, specify a fixed batch size for your model
        following the notes on statefulness RNNs.

    # References
        - [Recurrent Batch Normalization](https://arxiv.org/abs/1603.09025)
    '''
    def __init__(self, weights=None,
                 return_sequences=False, go_backwards=False, stateful=False,
                 unroll=False, consume_less='cpu',
                 input_dim=None, input_length=None,
                 batch_norm=False, batch_norm_gamma=0.1, **kwargs):
        self.return_sequences = return_sequences
        self.initial_weights = weights
        self.go_backwards = go_backwards
        self.stateful = stateful
        self.unroll = unroll
        self.consume_less = consume_less
        self.batch_norm = batch_norm
        self.batch_norm_gamma = batch_norm_gamma
        if self.batch_norm:
            self.uses_learning_phase = True
            self.beta_init = initializations.get('zero')
            self.epsilon = 1e-6
            self.momentum = 0.9
            self.batch_norm_gammas = []
            self.batch_norm_betas = []
            self.running_mean = []
            self.running_std = []

        self.supports_masking = True
        self.input_spec = [InputSpec(ndim=3)]
        self.input_dim = input_dim
        self.input_length = input_length
        if self.input_dim:
            kwargs['input_shape'] = (self.input_length, self.input_dim)
        super(Recurrent, self).__init__(**kwargs)

    def gamma_init(self, shape, name=None):
        return K.variable(np.ones(shape) * self.batch_norm_gamma, name=name)

    def get_output_shape_for(self, input_shape):
        if self.return_sequences:
            return (input_shape[0], input_shape[1], self.output_dim)
        else:
            return (input_shape[0], self.output_dim)

    def compute_mask(self, input, mask):
        if self.return_sequences:
            return mask
        else:
            return None

    def step(self, x, states):
        raise NotImplementedError

    def get_constants(self, x):
        return []

    def get_initial_states(self, x):
        # build an all-zero tensor of shape (samples, output_dim)
        initial_state = K.zeros_like(x)  # (samples, timesteps, input_dim)
        initial_state = K.sum(initial_state, axis=1)  # (samples, input_dim)
        reducer = K.zeros((self.input_dim, self.output_dim))
        initial_state = K.dot(initial_state, reducer)  # (samples, output_dim)
        initial_states = [initial_state for _ in range(len(self.states))]
        return initial_states

    def bn(self, x, field, loc=[0]):
        matrix_amount = len(loc)
        _gamma = K.gather(self.batch_norm_gammas[field], loc)
        _beta = K.gather(self.batch_norm_betas[field], loc)
        _mean = K.gather(self.running_mean[field], loc)
        _std = K.gather(self.running_std[field], loc)

        import theano
        _mean = theano.printing.Print("_mean = ")(_mean)

        _gamma = K.expand_dims(_gamma, dim=0) + K.sum(_mean)
        _beta = K.expand_dims(_beta, dim=0)
        x = K.reshape(x, [-1, matrix_amount, self.output_dim])
        x_mean = K.in_train_phase(K.mean(x, axis=[0, 2], keepdims=True), K.expand_dims(_mean, dim=0))

        # import theano
        # x_mean = theano.printing.Print("x_mean = ")(x_mean)

        x_var = x - x_mean
        x_std = K.in_train_phase(K.sqrt(K.mean(K.square(x_var), axis=[0, 2], keepdims=True) + self.epsilon), K.expand_dims(_std, dim=0))
        res = x_var / x_std * _gamma + _beta
        res = K.reshape(res, [-1, self.output_dim * matrix_amount])
        # updates
        update_mean = self.momentum * _mean + (1.0 - self.momentum) * x_mean
        update_std = self.momentum * _std + (1.0 - self.momentum) * x_std
        _mean = K.in_train_phase(update_mean, _mean)
        _std = K.in_train_phase(update_std, _std)
        #################################################
        # HOW TO UPDATE?
        #################################################
        return res

    def preprocess_input(self, x):
        return x

    def call(self, x, mask=None):
        # input shape: (nb_samples, time (padded with zeros), input_dim)
        # note that the .build() method of subclasses MUST define
        # self.input_spec with a complete input shape.
        input_shape = self.input_spec[0].shape
        if K._BACKEND == 'tensorflow':
            if not input_shape[1]:
                raise Exception('When using TensorFlow, you should define '
                                'explicitly the number of timesteps of '
                                'your sequences.\n'
                                'If your first layer is an Embedding, '
                                'make sure to pass it an "input_length" '
                                'argument. Otherwise, make sure '
                                'the first layer has '
                                'an "input_shape" or "batch_input_shape" '
                                'argument, including the time axis. '
                                'Found input shape at layer ' + self.name +
                                ': ' + str(input_shape))
        if self.stateful:
            initial_states = self.states
        else:
            initial_states = self.get_initial_states(x)
        constants = self.get_constants(x)
        preprocessed_input = self.preprocess_input(x)

        last_output, outputs, states = K.rnn(self.step, preprocessed_input,
                                             initial_states,
                                             go_backwards=self.go_backwards,
                                             mask=mask,
                                             constants=constants,
                                             unroll=self.unroll,
                                             input_length=input_shape[1])
        if self.stateful:
            self.updates = []
            for i in range(len(states)):
                self.updates.append((self.states[i], states[i]))

        if self.return_sequences:
            return outputs
        else:
            return last_output

    def get_config(self):
        config = {'return_sequences': self.return_sequences,
                  'go_backwards': self.go_backwards,
                  'stateful': self.stateful,
                  'unroll': self.unroll,
                  'consume_less': self.consume_less,
                  'batch_norm': self.batch_norm,
                  'batch_norm_gamma': self.batch_norm_gamma}
        if self.stateful:
            config['batch_input_shape'] = self.input_spec[0].shape
        else:
            config['input_dim'] = self.input_dim
            config['input_length'] = self.input_length

        base_config = super(Recurrent, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class SimpleRNN(Recurrent):
    '''Fully-connected RNN where the output is to be fed back to input.

    # Arguments
        output_dim: dimension of the internal projections and the final output.
        init: weight initialization function.
            Can be the name of an existing function (str),
            or a Theano function (see: [initializations](../initializations.md)).
        inner_init: initialization function of the inner cells.
        activation: activation function.
            Can be the name of an existing function (str),
            or a Theano function (see: [activations](../activations.md)).
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the input weights matrices.
        U_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the recurrent weights matrices.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        dropout_W: float between 0 and 1. Fraction of the input units to drop for input gates.
        dropout_U: float between 0 and 1. Fraction of the input units to drop for recurrent connections.

    # References
        - [A Theoretically Grounded Application of Dropout in Recurrent Neural Networks](http://arxiv.org/abs/1512.05287)
    '''
    def __init__(self, output_dim,
                 init='glorot_uniform', inner_init='orthogonal',
                 activation='tanh',
                 W_regularizer=None, U_regularizer=None, b_regularizer=None,
                 dropout_W=0., dropout_U=0., **kwargs):
        self.output_dim = output_dim
        self.init = initializations.get(init)
        self.inner_init = initializations.get(inner_init)
        self.activation = activations.get(activation)
        self.W_regularizer = regularizers.get(W_regularizer)
        self.U_regularizer = regularizers.get(U_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.dropout_W, self.dropout_U = dropout_W, dropout_U

        if self.dropout_W or self.dropout_U:
            self.uses_learning_phase = True
        super(SimpleRNN, self).__init__(**kwargs)

    def build(self, input_shape):
        self.input_spec = [InputSpec(shape=input_shape)]
        if self.stateful:
            self.reset_states()
        else:
            # initial states: all-zero tensor of shape (output_dim)
            self.states = [None]
        input_dim = input_shape[2]
        self.input_dim = input_dim

        self.W = self.init((input_dim, self.output_dim),
                           name='{}_W'.format(self.name))
        self.U = self.inner_init((self.output_dim, self.output_dim),
                                 name='{}_U'.format(self.name))
        self.b = K.zeros((self.output_dim,), name='{}_b'.format(self.name))

        if self.batch_norm:
            for field in ['input', 'recurrent']:
                _shape = (1, self.output_dim,)
                self.batch_norm_gammas.append(
                    self.gamma_init(_shape, name='{}_gamma_{}'.format(self.name, field))
                )
                self.batch_norm_betas.append(
                    self.beta_init(_shape, name='{}_beta_{}'.format(self.name, field))
                )
                self.running_mean.append(
                    K.zeros(_shape, name='{}_running_mean_{}'.format(self.name, field))
                )
                self.running_std.append(
                    K.ones(_shape, name='{}_running_std_{}'.format(self.name, field))
                )
            self.trainable_weights += self.batch_norm_gammas + self.batch_norm_betas
            self.trainable_weights += self.running_mean + self.running_std

        self.regularizers = []
        if self.W_regularizer:
            self.W_regularizer.set_param(self.W)
            self.regularizers.append(self.W_regularizer)
        if self.U_regularizer:
            self.U_regularizer.set_param(self.U)
            self.regularizers.append(self.U_regularizer)
        if self.b_regularizer:
            self.b_regularizer.set_param(self.b)
            self.regularizers.append(self.b_regularizer)

        self.trainable_weights = [self.W, self.U, self.b]

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights

    def reset_states(self):
        assert self.stateful, 'Layer must be stateful.'
        input_shape = self.input_spec[0].shape
        if not input_shape[0]:
            raise Exception('If a RNN is stateful, a complete ' +
                            'input_shape must be provided (including batch size).')
        if hasattr(self, 'states'):
            K.set_value(self.states[0],
                        np.zeros((input_shape[0], self.output_dim)))
        else:
            self.states = [K.zeros((input_shape[0], self.output_dim))]

    def preprocess_input(self, x):
        if self.consume_less == 'cpu':
            input_shape = self.input_spec[0].shape
            input_dim = input_shape[2]
            timesteps = input_shape[1]
            return time_distributed_dense(x, self.W, None, self.dropout_W,
                                          input_dim, self.output_dim,
                                          timesteps)
        else:
            return x

    def step(self, x, states):
        prev_output = states[0]
        B_U = states[1]
        B_W = states[2]

        if self.consume_less == 'cpu':
            input_to_hidden = x
        else:
            input_to_hidden = K.dot(x * B_W, self.W) + self.b

        hidden_to_hidden = K.dot(prev_output * B_U, self.U)
        if self.batch_norm:
            input_to_hidden = self.bn(input_to_hidden, field=0, loc=[0])
            hidden_to_hidden = self.bn(hidden_to_hidden, field=1, loc=[0])
        output = self.activation(input_to_hidden + hidden_to_hidden + self.b)
        return output, [output]

    def get_constants(self, x):
        constants = []
        if 0 < self.dropout_U < 1:
            ones = K.ones_like(K.reshape(x[:, 0, 0], (-1, 1)))
            ones = K.concatenate([ones] * self.output_dim, 1)
            B_U = K.in_train_phase(K.dropout(ones, self.dropout_U), ones)
            constants.append(B_U)
        else:
            constants.append(K.cast_to_floatx(1.))
        if self.consume_less == 'cpu' and 0 < self.dropout_W < 1:
            input_shape = self.input_spec[0].shape
            input_dim = input_shape[-1]
            ones = K.ones_like(K.reshape(x[:, 0, 0], (-1, 1)))
            ones = K.concatenate([ones] * input_dim, 1)
            B_W = K.in_train_phase(K.dropout(ones, self.dropout_W), ones)
            constants.append(B_W)
        else:
            constants.append(K.cast_to_floatx(1.))
        return constants

    def get_config(self):
        config = {'output_dim': self.output_dim,
                  'init': self.init.__name__,
                  'inner_init': self.inner_init.__name__,
                  'activation': self.activation.__name__,
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'U_regularizer': self.U_regularizer.get_config() if self.U_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'dropout_W': self.dropout_W,
                  'dropout_U': self.dropout_U}
        base_config = super(SimpleRNN, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class GRU(Recurrent):
    '''Gated Recurrent Unit - Cho et al. 2014.

    # Arguments
        output_dim: dimension of the internal projections and the final output.
        init: weight initialization function.
            Can be the name of an existing function (str),
            or a Theano function (see: [initializations](../initializations.md)).
        inner_init: initialization function of the inner cells.
        activation: activation function.
            Can be the name of an existing function (str),
            or a Theano function (see: [activations](../activations.md)).
        inner_activation: activation function for the inner cells.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the input weights matrices.
        U_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the recurrent weights matrices.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        dropout_W: float between 0 and 1. Fraction of the input units to drop for input gates.
        dropout_U: float between 0 and 1. Fraction of the input units to drop for recurrent connections.

    # References
        - [On the Properties of Neural Machine Translation: Encoder–Decoder Approaches](http://www.aclweb.org/anthology/W14-4012)
        - [Empirical Evaluation of Gated Recurrent Neural Networks on Sequence Modeling](http://arxiv.org/pdf/1412.3555v1.pdf)
        - [A Theoretically Grounded Application of Dropout in Recurrent Neural Networks](http://arxiv.org/abs/1512.05287)
    '''
    def __init__(self, output_dim,
                 init='glorot_uniform', inner_init='orthogonal',
                 activation='tanh', inner_activation='hard_sigmoid',
                 W_regularizer=None, U_regularizer=None, b_regularizer=None,
                 dropout_W=0., dropout_U=0., **kwargs):
        self.output_dim = output_dim
        self.init = initializations.get(init)
        self.inner_init = initializations.get(inner_init)
        self.activation = activations.get(activation)
        self.inner_activation = activations.get(inner_activation)
        self.W_regularizer = regularizers.get(W_regularizer)
        self.U_regularizer = regularizers.get(U_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.dropout_W, self.dropout_U = dropout_W, dropout_U

        if self.dropout_W or self.dropout_U:
            self.uses_learning_phase = True
        super(GRU, self).__init__(**kwargs)

    def build(self, input_shape):
        self.input_spec = [InputSpec(shape=input_shape)]
        self.input_dim = input_shape[2]

        if self.stateful:
            self.reset_states()
        else:
            # initial states: all-zero tensor of shape (output_dim)
            self.states = [None]

        if self.consume_less == 'gpu':

            self.W = self.init((self.input_dim, 3 * self.output_dim),
                               name='{}_W'.format(self.name))
            self.U = self.inner_init((self.output_dim, 3 * self.output_dim),
                                     name='{}_U'.format(self.name))

            self.b = K.variable(np.hstack((np.zeros(self.output_dim),
                                           np.zeros(self.output_dim),
                                           np.zeros(self.output_dim))),
                                name='{}_b'.format(self.name))

            self.trainable_weights = [self.W, self.U, self.b]
        else:

            self.W_z = self.init((self.input_dim, self.output_dim),
                                 name='{}_W_z'.format(self.name))
            self.U_z = self.inner_init((self.output_dim, self.output_dim),
                                       name='{}_U_z'.format(self.name))
            self.b_z = K.zeros((self.output_dim,), name='{}_b_z'.format(self.name))

            self.W_r = self.init((self.input_dim, self.output_dim),
                                 name='{}_W_r'.format(self.name))
            self.U_r = self.inner_init((self.output_dim, self.output_dim),
                                       name='{}_U_r'.format(self.name))
            self.b_r = K.zeros((self.output_dim,), name='{}_b_r'.format(self.name))

            self.W_h = self.init((self.input_dim, self.output_dim),
                                 name='{}_W_h'.format(self.name))
            self.U_h = self.inner_init((self.output_dim, self.output_dim),
                                       name='{}_U_h'.format(self.name))
            self.b_h = K.zeros((self.output_dim,), name='{}_b_h'.format(self.name))

            self.trainable_weights = [self.W_z, self.U_z, self.b_z,
                                      self.W_r, self.U_r, self.b_r,
                                      self.W_h, self.U_h, self.b_h]

            self.W = K.concatenate([self.W_z, self.W_r, self.W_h])
            self.U = K.concatenate([self.U_z, self.U_r, self.U_h])
            self.b = K.concatenate([self.b_z, self.b_r, self.b_h])

        if self.batch_norm:
            for field in ['input', 'recurrent']:
                _shape = (3, self.output_dim,)
                self.batch_norm_gammas.append(
                    self.gamma_init(_shape, name='{}_gamma_{}'.format(self.name, field))
                )
                self.batch_norm_betas.append(
                    self.beta_init(_shape, name='{}_beta_{}'.format(self.name, field))
                )
                self.running_mean.append(
                    K.zeros(_shape, name='{}_running_mean_{}'.format(self.name, field))
                )
                self.running_std.append(
                    K.ones(_shape, name='{}_running_std_{}'.format(self.name, field))
                )
            self.trainable_weights += self.batch_norm_gammas + self.batch_norm_betas

        self.regularizers = []
        if self.W_regularizer:
            self.W_regularizer.set_param(self.W)
            self.regularizers.append(self.W_regularizer)
        if self.U_regularizer:
            self.U_regularizer.set_param(self.U)
            self.regularizers.append(self.U_regularizer)
        if self.b_regularizer:
            self.b_regularizer.set_param(self.b)
            self.regularizers.append(self.b_regularizer)

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights

    def reset_states(self):
        assert self.stateful, 'Layer must be stateful.'
        input_shape = self.input_spec[0].shape
        if not input_shape[0]:
            raise Exception('If a RNN is stateful, a complete ' +
                            'input_shape must be provided (including batch size).')
        if hasattr(self, 'states'):
            K.set_value(self.states[0],
                        np.zeros((input_shape[0], self.output_dim)))
        else:
            self.states = [K.zeros((input_shape[0], self.output_dim))]

    def preprocess_input(self, x):
        if self.consume_less == 'cpu':
            input_shape = self.input_spec[0].shape
            input_dim = input_shape[2]
            timesteps = input_shape[1]

            x_z = time_distributed_dense(x, self.W_z, None, self.dropout_W,
                                         input_dim, self.output_dim, timesteps)
            x_r = time_distributed_dense(x, self.W_r, None, self.dropout_W,
                                         input_dim, self.output_dim, timesteps)
            x_h = time_distributed_dense(x, self.W_h, None, self.dropout_W,
                                         input_dim, self.output_dim, timesteps)
            return K.concatenate([x_z, x_r, x_h], axis=2)
        else:
            return x

    def step(self, x, states):
        h_tm1 = states[0]  # previous memory
        B_U = states[1]  # dropout matrices for recurrent units
        B_W = states[2]

        if self.consume_less == 'gpu':

            input_to_hidden = K.dot(x * B_W[0], self.W)
            hidden_to_hidden = K.dot(h_tm1 * B_U[0], self.U[:, :2 * self.output_dim])
            if self.batch_norm:
                input_to_hidden = self.bn(input_to_hidden, field=0, loc=[0, 1, 2])
                hidden_to_hidden = self.bn(hidden_to_hidden, field=1, loc=[0, 1])
            input_to_hidden += self.b

            x_z = input_to_hidden[:, :self.output_dim]
            x_r = input_to_hidden[:, self.output_dim: 2 * self.output_dim]
            inner_z = hidden_to_hidden[:, :self.output_dim]
            inner_r = hidden_to_hidden[:, self.output_dim: 2 * self.output_dim]

            z = self.inner_activation(x_z + inner_z)
            r = self.inner_activation(x_r + inner_r)

            x_h = input_to_hidden[:, 2 * self.output_dim:]
            inner_h = K.dot(r * h_tm1 * B_U[0], self.U[:, 2 * self.output_dim:])
            if self.batch_norm:
                inner_h = self.bn(inner_h, K.gather(self.batch_norm_gammas[1], 2), K.gather(self.batch_norm_betas[1], 2))
            hh = self.activation(x_h + inner_h)

        else:
            if self.consume_less == 'cpu':
                x_z = x[:, :self.output_dim]
                x_r = x[:, self.output_dim: 2 * self.output_dim]
                x_h = x[:, 2 * self.output_dim:]
            elif self.consume_less == 'mem':
                x_z = K.dot(x * B_W[0], self.W_z) + self.b_z
                x_r = K.dot(x * B_W[1], self.W_r) + self.b_r
                x_h = K.dot(x * B_W[2], self.W_h) + self.b_h
            else:
                raise Exception('Unknown `consume_less` mode.')

            h_z = K.dot(h_tm1 * B_U[0], self.U_z)
            h_r = K.dot(h_tm1 * B_U[1], self.U_r)

            if self.batch_norm:
                x_z = self.bn(x_z, field=0, loc=[0])
                x_r = self.bn(x_r, field=0, loc=[1])
                x_h = self.bn(x_h, field=0, loc=[2])

                h_z = self.bn(h_z, field=1, loc=[0])
                h_r = self.bn(h_r, field=1, loc=[1])

            z = self.inner_activation(x_z + h_z + self.b_z)
            r = self.inner_activation(x_r + h_r + self.b_r)
            h_h = K.dot(r * h_tm1 * B_U[2], self.U_h)
            if self.batch_norm:
                h_h = self.bn(h_h, field=1, loc=[2])

            hh = self.activation(x_h + h_h + self.b_h)

        h = z * h_tm1 + (1 - z) * hh
        return h, [h]

    def get_constants(self, x):
        constants = []
        if 0 < self.dropout_U < 1:
            ones = K.ones_like(K.reshape(x[:, 0, 0], (-1, 1)))
            ones = K.concatenate([ones] * self.output_dim, 1)
            B_U = [K.in_train_phase(K.dropout(ones, self.dropout_U), ones) for _ in range(3)]
            constants.append(B_U)
        else:
            constants.append([K.cast_to_floatx(1.) for _ in range(3)])

        if 0 < self.dropout_W < 1:
            input_shape = self.input_spec[0].shape
            input_dim = input_shape[-1]
            ones = K.ones_like(K.reshape(x[:, 0, 0], (-1, 1)))
            ones = K.concatenate([ones] * input_dim, 1)
            B_W = [K.in_train_phase(K.dropout(ones, self.dropout_W), ones) for _ in range(3)]
            constants.append(B_W)
        else:
            constants.append([K.cast_to_floatx(1.) for _ in range(3)])
        return constants

    def get_config(self):
        config = {'output_dim': self.output_dim,
                  'init': self.init.__name__,
                  'inner_init': self.inner_init.__name__,
                  'activation': self.activation.__name__,
                  'inner_activation': self.inner_activation.__name__,
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'U_regularizer': self.U_regularizer.get_config() if self.U_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'dropout_W': self.dropout_W,
                  'dropout_U': self.dropout_U}
        base_config = super(GRU, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class LSTM(Recurrent):
    '''Long-Short Term Memory unit - Hochreiter 1997.

    For a step-by-step description of the algorithm, see
    [this tutorial](http://deeplearning.net/tutorial/lstm.html).

    # Arguments
        output_dim: dimension of the internal projections and the final output.
        init: weight initialization function.
            Can be the name of an existing function (str),
            or a Theano function (see: [initializations](../initializations.md)).
        inner_init: initialization function of the inner cells.
        forget_bias_init: initialization function for the bias of the forget gate.
            [Jozefowicz et al.](http://www.jmlr.org/proceedings/papers/v37/jozefowicz15.pdf)
            recommend initializing with ones.
        activation: activation function.
            Can be the name of an existing function (str),
            or a Theano function (see: [activations](../activations.md)).
        inner_activation: activation function for the inner cells.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the input weights matrices.
        U_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the recurrent weights matrices.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        dropout_W: float between 0 and 1. Fraction of the input units to drop for input gates.
        dropout_U: float between 0 and 1. Fraction of the input units to drop for recurrent connections.

    # References
        - [Long short-term memory](http://deeplearning.cs.cmu.edu/pdfs/Hochreiter97_lstm.pdf) (original 1997 paper)
        - [Learning to forget: Continual prediction with LSTM](http://www.mitpressjournals.org/doi/pdf/10.1162/089976600300015015)
        - [Supervised sequence labelling with recurrent neural networks](http://www.cs.toronto.edu/~graves/preprint.pdf)
        - [A Theoretically Grounded Application of Dropout in Recurrent Neural Networks](http://arxiv.org/abs/1512.05287)
    '''
    def __init__(self, output_dim,
                 init='glorot_uniform', inner_init='orthogonal',
                 forget_bias_init='one', activation='tanh',
                 inner_activation='hard_sigmoid',
                 W_regularizer=None, U_regularizer=None, b_regularizer=None,
                 dropout_W=0., dropout_U=0., **kwargs):
        self.output_dim = output_dim
        self.init = initializations.get(init)
        self.inner_init = initializations.get(inner_init)
        self.forget_bias_init = initializations.get(forget_bias_init)
        self.activation = activations.get(activation)
        self.inner_activation = activations.get(inner_activation)
        self.W_regularizer = regularizers.get(W_regularizer)
        self.U_regularizer = regularizers.get(U_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.dropout_W, self.dropout_U = dropout_W, dropout_U

        if self.dropout_W or self.dropout_U:
            self.uses_learning_phase = True
        super(LSTM, self).__init__(**kwargs)

    def build(self, input_shape):
        self.input_spec = [InputSpec(shape=input_shape)]
        self.input_dim = input_shape[2]

        if self.stateful:
            self.reset_states()
        else:
            # initial states: 2 all-zero tensors of shape (output_dim)
            self.states = [None, None]

        if self.consume_less == 'gpu':
            self.W = self.init((self.input_dim, 4 * self.output_dim),
                               name='{}_W'.format(self.name))
            self.U = self.inner_init((self.output_dim, 4 * self.output_dim),
                                     name='{}_U'.format(self.name))

            self.b = K.variable(np.hstack((np.zeros(self.output_dim),
                                           K.get_value(self.forget_bias_init(self.output_dim)),
                                           np.zeros(self.output_dim),
                                           np.zeros(self.output_dim))),
                                name='{}_b'.format(self.name))
            self.trainable_weights = [self.W, self.U, self.b]

        else:
            self.W_i = self.init((self.input_dim, self.output_dim),
                                 name='{}_W_i'.format(self.name))
            self.U_i = self.inner_init((self.output_dim, self.output_dim),
                                       name='{}_U_i'.format(self.name))
            self.b_i = K.zeros((self.output_dim,), name='{}_b_i'.format(self.name))

            self.W_f = self.init((self.input_dim, self.output_dim),
                                 name='{}_W_f'.format(self.name))
            self.U_f = self.inner_init((self.output_dim, self.output_dim),
                                       name='{}_U_f'.format(self.name))
            self.b_f = self.forget_bias_init((self.output_dim,),
                                             name='{}_b_f'.format(self.name))

            self.W_c = self.init((self.input_dim, self.output_dim),
                                 name='{}_W_c'.format(self.name))
            self.U_c = self.inner_init((self.output_dim, self.output_dim),
                                       name='{}_U_c'.format(self.name))
            self.b_c = K.zeros((self.output_dim,), name='{}_b_c'.format(self.name))

            self.W_o = self.init((self.input_dim, self.output_dim),
                                 name='{}_W_o'.format(self.name))
            self.U_o = self.inner_init((self.output_dim, self.output_dim),
                                       name='{}_U_o'.format(self.name))
            self.b_o = K.zeros((self.output_dim,), name='{}_b_o'.format(self.name))

            self.trainable_weights = [self.W_i, self.U_i, self.b_i,
                                      self.W_c, self.U_c, self.b_c,
                                      self.W_f, self.U_f, self.b_f,
                                      self.W_o, self.U_o, self.b_o]

            self.W = K.concatenate([self.W_i, self.W_f, self.W_c, self.W_o])
            self.U = K.concatenate([self.U_i, self.U_f, self.U_c, self.U_o])
            self.b = K.concatenate([self.b_i, self.b_f, self.b_c, self.b_o])

        if self.batch_norm:
            for field in ['input', 'recurrent', 'output']:
                _shape = (1, self.output_dim,) if field == 'output' else (4, self.output_dim,)
                self.batch_norm_gammas.append(
                    self.gamma_init(_shape, name='{}_gamma_{}'.format(self.name, field))
                )
                self.batch_norm_betas.append(
                    self.beta_init(_shape, name='{}_beta_{}'.format(self.name, field))
                )
                self.running_mean.append(
                    K.zeros(_shape, name='{}_running_mean_{}'.format(self.name, field))
                )
                self.running_std.append(
                    K.ones(_shape, name='{}_running_std_{}'.format(self.name, field))
                )
            self.trainable_weights += self.batch_norm_gammas + self.batch_norm_betas

        self.regularizers = []
        if self.W_regularizer:
            self.W_regularizer.set_param(self.W)
            self.regularizers.append(self.W_regularizer)
        if self.U_regularizer:
            self.U_regularizer.set_param(self.U)
            self.regularizers.append(self.U_regularizer)
        if self.b_regularizer:
            self.b_regularizer.set_param(self.b)
            self.regularizers.append(self.b_regularizer)

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights

    def reset_states(self):
        assert self.stateful, 'Layer must be stateful.'
        input_shape = self.input_spec[0].shape
        if not input_shape[0]:
            raise Exception('If a RNN is stateful, a complete ' +
                            'input_shape must be provided (including batch size).')
        if hasattr(self, 'states'):
            K.set_value(self.states[0],
                        np.zeros((input_shape[0], self.output_dim)))
            K.set_value(self.states[1],
                        np.zeros((input_shape[0], self.output_dim)))
        else:
            self.states = [K.zeros((input_shape[0], self.output_dim)),
                           K.zeros((input_shape[0], self.output_dim))]

    def preprocess_input(self, x):
        if self.consume_less == 'cpu':
            if 0 < self.dropout_W < 1:
                dropout = self.dropout_W
            else:
                dropout = 0
            input_shape = self.input_spec[0].shape
            input_dim = input_shape[2]
            timesteps = input_shape[1]

            x_i = time_distributed_dense(x, self.W_i, None, dropout,
                                         input_dim, self.output_dim, timesteps)
            x_f = time_distributed_dense(x, self.W_f, None, dropout,
                                         input_dim, self.output_dim, timesteps)
            x_c = time_distributed_dense(x, self.W_c, None, dropout,
                                         input_dim, self.output_dim, timesteps)
            x_o = time_distributed_dense(x, self.W_o, None, dropout,
                                         input_dim, self.output_dim, timesteps)
            return K.concatenate([x_i, x_f, x_c, x_o], axis=2)
        else:
            return x

    def step(self, x, states):
        h_tm1 = states[0]
        c_tm1 = states[1]
        B_U = states[2]
        B_W = states[3]

        if self.consume_less == 'gpu':
            input_to_hidden = K.dot(x * B_W[0], self.W)
            hidden_to_hidden = K.dot(h_tm1 * B_U[0], self.U)
            if self.batch_norm:
                input_to_hidden = self.bn(input_to_hidden, field=0, loc=[0, 1, 2, 3])
                hidden_to_hidden = self.bn(hidden_to_hidden, field=1, loc=[0, 1, 2, 3])
            z = input_to_hidden + hidden_to_hidden + self.b

            z0 = z[:, :self.output_dim]
            z1 = z[:, self.output_dim: 2 * self.output_dim]
            z2 = z[:, 2 * self.output_dim: 3 * self.output_dim]
            z3 = z[:, 3 * self.output_dim:]

            i = self.inner_activation(z0)
            f = self.inner_activation(z1)
            c = f * c_tm1 + i * self.activation(z2)
            c_h = self.bn(c, field=2, loc=[0]) if self.batch_norm else c
            o = self.inner_activation(z3)
        else:
            if self.consume_less == 'cpu':
                x_i = x[:, :self.output_dim]
                x_f = x[:, self.output_dim: 2 * self.output_dim]
                x_c = x[:, 2 * self.output_dim: 3 * self.output_dim]
                x_o = x[:, 3 * self.output_dim:]
            elif self.consume_less == 'mem':
                x_i = K.dot(x * B_W[0], self.W_i)
                x_f = K.dot(x * B_W[1], self.W_f)
                x_c = K.dot(x * B_W[2], self.W_c)
                x_o = K.dot(x * B_W[3], self.W_o)
            else:
                raise Exception('Unknown `consume_less` mode.')

            h_i = K.dot(h_tm1 * B_U[0], self.U_i)
            h_f = K.dot(h_tm1 * B_U[1], self.U_f)
            h_c = K.dot(h_tm1 * B_U[2], self.U_c)
            h_o = K.dot(h_tm1 * B_U[3], self.U_o)
            if self.batch_norm:
                x_i = self.bn(x_i, field=0, loc=[0])
                x_f = self.bn(x_f, field=0, loc=[1])
                x_c = self.bn(x_c, field=0, loc=[2])
                x_o = self.bn(x_o, field=0, loc=[3])

                h_i = self.bn(h_i, field=1, loc=[0])
                h_f = self.bn(h_f, field=1, loc=[1])
                h_c = self.bn(h_c, field=1, loc=[2])
                h_o = self.bn(h_o, field=1, loc=[3])

            i = self.inner_activation(x_i + h_i + self.b_i)
            f = self.inner_activation(x_f + h_f + self.b_f)
            c = f * c_tm1 + i * self.activation(x_c + h_c + self.b_c)
            c_h = self.bn(c, field=2, loc=[0]) if self.batch_norm else c
            o = self.inner_activation(x_o + h_o + self.b_o)

        h = o * self.activation(c_h)
        return h, [h, c]

    def get_constants(self, x):
        constants = []
        if 0 < self.dropout_U < 1:
            ones = K.ones_like(K.reshape(x[:, 0, 0], (-1, 1)))
            ones = K.concatenate([ones] * self.output_dim, 1)
            B_U = [K.in_train_phase(K.dropout(ones, self.dropout_U), ones) for _ in range(4)]
            constants.append(B_U)
        else:
            constants.append([K.cast_to_floatx(1.) for _ in range(4)])

        if 0 < self.dropout_W < 1:
            input_shape = self.input_spec[0].shape
            input_dim = input_shape[-1]
            ones = K.ones_like(K.reshape(x[:, 0, 0], (-1, 1)))
            ones = K.concatenate([ones] * input_dim, 1)
            B_W = [K.in_train_phase(K.dropout(ones, self.dropout_W), ones) for _ in range(4)]
            constants.append(B_W)
        else:
            constants.append([K.cast_to_floatx(1.) for _ in range(4)])
        return constants

    def get_config(self):
        config = {'output_dim': self.output_dim,
                  'init': self.init.__name__,
                  'inner_init': self.inner_init.__name__,
                  'forget_bias_init': self.forget_bias_init.__name__,
                  'activation': self.activation.__name__,
                  'inner_activation': self.inner_activation.__name__,
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'U_regularizer': self.U_regularizer.get_config() if self.U_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'dropout_W': self.dropout_W,
                  'dropout_U': self.dropout_U}
        base_config = super(LSTM, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))
