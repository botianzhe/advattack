import robustml
from robustml_model import SAP
import sys
import argparse
import tensorflow as tf
import numpy as np

class Attack:
    def __init__(self, sess, model, epsilon, tol=1, num_steps=500, step_size=.1, random_start=False):
        self._sess = sess
        self.model = model
        self.tol = tol
        self.num_steps = num_steps
        self.step_size = step_size
        self.rand = random_start

        self.xs = tf.Variable(np.zeros((1, 32, 32, 3), dtype=np.float32),
                                    name='modifier')
        self.orig_xs = tf.placeholder(tf.float32, [None, 32, 32, 3])

        self.ys = tf.placeholder(tf.int32, [None])

        self.epsilon = epsilon * 255

        delta = tf.clip_by_value(self.xs, 0, 255) - self.orig_xs
        delta = tf.clip_by_value(delta, -self.epsilon, self.epsilon)

        self.do_clip_xs = tf.assign(self.xs, self.orig_xs+delta)

        self.logits = logits = model(self.xs)

        label_mask = tf.one_hot(self.ys, 10)
        correct_logit = tf.reduce_sum(label_mask * logits, axis=1)
        wrong_logit = tf.reduce_max((1-label_mask) * logits - 1e4*label_mask, axis=1)

        self.loss = (correct_logit - wrong_logit)

        start_vars = set(x.name for x in tf.global_variables())
        optimizer = tf.train.AdamOptimizer(step_size*1)

        grad,var = optimizer.compute_gradients(self.loss, [self.xs])[0]
        self.train = optimizer.apply_gradients([(tf.sign(grad),var)])

        end_vars = tf.global_variables()
        self.new_vars = [x for x in end_vars if x.name not in start_vars]

    def perturb(self, x, y, sess):
        sess.run(tf.variables_initializer(self.new_vars))
        sess.run(self.xs.initializer)
        sess.run(self.do_clip_xs,
                 {self.orig_xs: x})

        for i in range(self.num_steps):

            sess.run(self.train, feed_dict={self.ys: y})
            sess.run(self.do_clip_xs,
                     {self.orig_xs: x})

        return sess.run(self.xs)

    def run(self, x, y, target):
        if target is not None:
            raise NotImplementedError
        return self.perturb(np.array([x]) * 255.0, [y], self._sess)[0] / 255.0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cifar-path', type=str, required=True,
            help='path to the test_batch file from http://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end', type=int, default=100)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    # set up TensorFlow session
    sess = tf.Session()

    # initialize a model
    model = SAP(sess)

    # initialize an attack (it's a white box attack, and it's allowed to look
    # at the internals of the model in any way it wants)
    # attack = BPDA(sess, model, epsilon=model.threat_model.epsilon, debug=args.debug)
    attack = Attack(sess, model.model, epsilon=model.threat_model.epsilon)

    # initialize a data provider for CIFAR-10 images
    provider = robustml.provider.CIFAR10(args.cifar_path)

    success_rate = robustml.evaluate.evaluate(
        model,
        attack,
        provider,
        start=args.start,
        end=args.end,
        deterministic=True,
        debug=args.debug,
    )

    print('attack success rate: %.2f%% (over %d data points)' % (success_rate*100, args.end-args.start))

if __name__ == '__main__':
    main()
