from __future__ import print_function

import paddle
import paddle.fluid as fluid
import contextlib
import numpy
import unittest
import math
import sys
import os

def train(use_cuda, save_dirname, is_local):
	# step 1.1 : 输入
	x = fluid.layers.data(name='x', shape=[13], dtype='float32')
	y = fluid.layers.data(name='y', shape=[1], dtype='float32')
	# step 1.2 : 前向传播
	y_predict = fluid.layers.fc(input=x, size=1, act=None)
	# step 1.3 : 成本函数
	cost = fluid.layers.square_error_cost(input=y_predict, label=y)
	avg_cost = fluid.layers.mean(cost)
	# step 1.4 : 随机梯度下降
	sgd_optimizer = fluid.optimizer.SGD(learning_rate=0.001)
	sgd_optimizer.minimize(avg_cost)

	# step 2.1 : 数据读取
	BATCH_SIZE = 20
	train_reader = paddle.batch(
		paddle.reader.shuffle(paddle.dataset.uci_housing.train(), buf_size=500),
		batch_size=BATCH_SIZE)
	# step 2.2 : 计算场地
	place = fluid.CUDAPlace(0) if use_cuda else fluid.CPUPlace()
	exe = fluid.Executor(place)
	def train_loop(main_program):
		feeder = fluid.DataFeeder(place=place, feed_list=[x,y])
		exe.run(fluid.default_startup_program()) 
		PASS_NUM = 100
		for pass_id in range(PASS_NUM):
			for data in train_reader():
				avg_loss_value = exe.run(main_program, feeder=feeder.feed(data), fetch_list=[avg_cost])
				print(avg_loss_value)
				if avg_loss_value[0] < 10.0:
					if save_dirname is not None:
						fluid.io.save_inference_model(save_dirname, ['x'], [y_predict], exe)
					return
				if math.isnan(float(avg_loss_value)):
					sys.exit("got NaN loss, training failed.")
		raise AssertionError("Fit a line cost is too large, {0:2.2}".format(avg_loss_value[0]))
	if is_local:
		train_loop(fluid.default_main_program())
	else:
		port = os.getenv("PADDLE_PSERVER_PORT", "6174")
		pserver_ips = os.getenv("PADDLE_PSERVER_PORT")
		eplist = []
		for ip in pserver_ips.split(","):
			eplist.append(':'.join([ip, port]))
		pserver_endpoints = ",".join(eplist)
		trainers = int(os.getenv("PADDLE_TRAINERS"))
		current_endpoint = os.getenv("POD_IP") + ":" + port
		trainer_id = int(os.getenv("PADDLE_TRAINER_ID"))
		training_role = os.getenv("PADDLE_TRAINER_ROLE", "TRAINER")
		t = fluid.DistributeTranspiler()
		t.transpile(trainer_id, pservers=pserver_endpoints, trainers=trainers)
		if training_role == "PSERVER":
			pserver_prog = t.get_pserver_program(current_endpoint)
			pserver_startup = t.get_startup_program(current_endpoint, pserver_prog)
			exe.run(pserver_startup)
			exe.run(pserver_prog)
		elif training_role == "TRAINER":
			train_loop(t.get_trainer_program())
def infer(use_cuda, save_dirname=None):
	if save_dirname is None:
		return
	place = fluid.CUDAPlace(0) if use_cuda else fluid.CPUPlace()
	exe = fluid.Executor(place)

	inference_scope = fluid.core.Scope()
	with fluid.scope_guard(inference_scope):
		[inference_program, feed_target_names, fetch_targets] = fluid.io.load_inference_model(save_dirname,exe)
		batch_size = 10
		test_reader = paddle.batch(paddle.dataset.uci_housing.test(), batch_size=batch_size)
		test_data = next(test_reader())
		test_feat = numpy.array([data[0] for data in test_data]).astype("float32")
		test_label = numpy.array([data[1] for data in test_data]).astype("float32")

		assert feed_target_names[0] == 'x'
		results = exe.run(inference_program,
			feed={feed_target_names[0]:numpy.array(test_feat)},
			fetch_list=fetch_targets)
		print("infer shape :", results[0].shape)
		print("infer results :", results[0])
		print("ground truth :", test_label)
def main(use_cuda, is_local=True):
	if use_cuda and not fluid.core.is_compiled_with_cuda():
		return
	save_dirname = "fit_a_line.inference.model"
	trin(use_cuda, save_dirname, is_local)
	infer(use_cuda, save_dirname)
class TestFitALine(unittest.TestCase):
	def test_cpu(self):
		with self.program_score_guard():
			main(use_cuda=False)
	def test_cuda(self):
		with self.program_score_guard():
			main(use_cuda=True)
	@contextlib.contextmanager
	def program_score_guard(self):
		prog = fluid.Program()
		startup_prog = fluid.Program()
		scope = fluid.core.Scope()
		with fluid.scope_guard(scope):
			with fluid.program_guard(prog, startup_prog):
				yield
if __name__ == "__main__":
	unittest.main()