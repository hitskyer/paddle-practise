import paddle
import paddle.fluid as fluid
import numpy as np
class SimpleImgConvPool(fluid.dygraph.Layer):
	def __init__(self,
			num_channels,
			num_filters,
			filter_size,
			pool_size,
			pool_stride,
			pool_padding=0,
			pool_type='max',
			global_pooling=False,
			conv_stride=1,
			conv_padding=0,
			conv_dilation=1,
			conv_groups=1,
			act=None,
			use_cudnn=False,
			param_attr=None,
			bias_attr=None):
		super(SimpleImgConvPool, self).__init__()

		self._conv2d = fluid.dygraph.Conv2D(
			num_channels=num_channels,
			num_filters=num_filters,
			filter_size=filter_size,
			stride=conv_stride,
			padding=conv_padding,
			dilation=conv_dilation,
			groups=conv_groups,
			param_attr=param_attr,
			bias_attr=bias_attr,
			act=act,
			use_cudnn=use_cudnn)
		self._pool2d = fluid.dygraph.Pool2D(
			pool_size=pool_size,
			pool_type=pool_type,
			pool_stride=pool_stride,
			pool_padding=pool_padding,
			global_pooling=global_pooling,
			use_cudnn=use_cudnn)
	def forward(self, inputs):
		x = self._conv2d(inputs)
		x = self._pool2d(x)
		return x
class MNIST(fluid.dygraph.Layer):
	def __init__(self, use_cudnn=False):
		super(MNIST, self).__init__()
		self._simple_img_conv_pool_1 = SimpleImgConvPool(
			1, 20, 5, 2, 2, act="relu", use_cudnn=use_cudnn)
		self._simple_img_conv_pool_2 = SimpleImgConvPool(
			20, 50, 5, 2, 2, act="relu", use_cudnn=use_cudnn)
		self.pool_2_shape = 50 * 4 * 4
		SIZE = 10
		scale = (2.0/(self.pool_2_shape**2 * SIZE))**0.5
		self._fc = fluid.dygraph.Linear(
			self.pool_2_shape,
			10,
			param_attr=fluid.param_attr.ParamAttr(
				initializer=fluid.initializer.NormalInitializer(
					loc=0.0, scale=scale)),
				act="softmax")
	def forward(self, inputs, label=None):
		x = self._simple_img_conv_pool_1(inputs)
		x = self._simple_img_conv_pool_2(x)
		x = fluid.layers.reshape(x, shape=[-1, self.pool_2_shape])
		x = self._fc(x)
		if label is not None:
			acc = fluid.layers.accuracy(input=x, label=label)
			return x, acc
		else:
			return x
