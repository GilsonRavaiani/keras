# -*- coding: utf-8 -*-
from __future__ import absolute_import

from .. import backend as K
from .. import initializations, regularizers, constraints
from ..engine import Layer, InputSpec


def sparse_chain_crf_loss(y, x, U, b):
    '''Given the true sparsely encoded tag sequences y, observations x,
    transition params U and label bias b, it computes the loss function
    of a Linear Chain Conditional Random Field.
    '''
    energy = K.crf_path_energy(y, x, U, b)
    energy -= K.crf_free_energy(x, U, b)
    return -energy


def chain_crf_loss(y, x, U, b):
    '''Given the true tag sequences y as one-hot encoded vectors,
    observations x, transition params U and label bias b, it computes the loss
    function of a Linear Chain Conditional Random Field.
    '''
    y_sparse = K.argmax(y, -1)
    y_sparse = K.cast(y_sparse, 'int32')
    return sparse_chain_crf_loss(y_sparse, x, U, b)


class ChainCRF(Layer):
    '''A Linear Chain Conditional Random Field output layer.

    It carries the loss function and its weights for computing
    the global tag sequence scores. While training it acts as
    the identity function that passes the inputs to the subsequently
    used loss function. While testing it applies Viterbi decoding
    and the best scoring tag sequence as one-hot encoded vectors.

    # Arguments
        init: weight initialization function.
            Can be the name of an existing function (str),
            or a Theano function (see: [initializations](../initializations.md)).
        U_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the transition weight matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.

    # Input shape
        3D tensor with shape `(nb_samples, timesteps, nb_classes)`, where
        ´timesteps >= 2`and `nb_classes >= 2`.

    # Output shape
        Same shape as input.

    # Masking
        Masing is currently not supported.

    # Example

    ```python
    # As the last layer of sequential layer with
    # model.output_shape == (None, timesteps, nb_classes)
    crf = ChainCRF()
    model.add(crf)
    # now: model.output_shape == (None, timesteps, nb_classes)

    # Compile model with chain crf loss (and one-hot encoded labels) and accuracy
    model.compile(loss=crf.loss, optimizer='sgd', metrics=['accuracy'])

    # Alternatively, compile model with sparsely encoded labels and sparse accuracy:
    model.compile(loss=crf.sparse_loss, optimizer='sgd', metrics=['sparse_categorical_accuracy'])
    ```
    '''
    def __init__(self, init='glorot_uniform',
                 U_regularizer=None, b_regularizer=None,
                 U_constraint=None, b_constraint=None,
                 **kwargs):
        self.supports_masking = False
        self.uses_learning_phase = True
        self.input_spec = [InputSpec(ndim=3)]
        self.init = initializations.get(init)

        self.U_regularizer = regularizers.get(U_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.U_constraint = constraints.get(U_constraint)
        self.b_constraint = constraints.get(b_constraint)

        super(ChainCRF, self).__init__(**kwargs)

    def get_output_shape_for(self, input_shape):
        assert input_shape and len(input_shape) == 3
        return (input_shape[0], input_shape[1], input_shape[2])

    def build(self, input_shape):
        assert len(input_shape) == 3
        n_classes = input_shape[2]
        n_steps = input_shape[1]
        assert n_classes >= 2
        assert n_steps >= 2
        self.input_spec = [InputSpec(dtype=K.floatx(),
                                     shape=(None, n_steps, n_classes))]
        self.U = self.init((n_classes, n_classes),
                           name='{}_U'.format(self.name))
        self.b = K.zeros((n_classes, ), name='{}_b'.format(self.name))
        self.trainable_weights = [self.U, self.b]

        self.regularizers = []
        if self.U_regularizer:
            self.U_regularizer.set_param(self.U)
            self.regularizers.append(self.U_regularizer)
        if self.b_regularizer:
            self.b_regularizer.set_param(self.b)
            self.regularizers.append(self.b_regularizer)

        self.constraints = {}
        if self.U_constraint:
            self.constraints[self.U] = self.U_constraint
        if self.b_constraint:
            self.constraints[self.b] = self.b_constraint
        self.built = True

    def call(self, x, mask=None):
        y_pred = K.crf_inference(x, self.U, self.b)
        y_pred_one_hot = K.one_hot(y_pred, self.input_spec[0].shape[2])
        return K.in_train_phase(x, y_pred_one_hot)

    def loss(self, y_true, y_pred):
        '''Linear Chain Conditional Random Field loss function.
        '''
        return chain_crf_loss(y_true, y_pred, self.U, self.b)

    def sparse_loss(self, y_true, y_pred):
        '''Linear Chain Conditional Random Field loss function with sparse
        tag sequences.
        '''
        y_true = K.cast(y_true, 'int32')
        y_true = K.squeeze(y_true, 2)
        return sparse_chain_crf_loss(y_true, y_pred, self.U, self.b)

    def get_config(self):
        config = {'init': self.init.__name__,
                  'U_regularizer': self.U_regularizer.get_config() if self.U_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'U_constraint': self.U_constraint.get_config() if self.U_constraint else None,
                  'b_constraint': self.b_constraint.get_config() if self.b_constraint else None,
                  }
        base_config = super(ChainCRF, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))
