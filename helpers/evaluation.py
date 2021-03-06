from __future__ import division

import numpy as np
import scipy.sparse as ssp
import os.path
import theano
import theano.tensor as T
import random
import operator
import collections
#import matplotlib.pyplot as plt

# Plot multiple figures at the same time
#plt.ion()

class Evaluator(object):
	'''Evaluator is a class to compute metrics on tests

	It is used by first adding a series of "instances" : pairs of goals and predictions, then metrics can be computed on the ensemble of instances:
	average precision, percentage of instance with a correct prediction, etc.

	It can also return the set of correct predictions.
	'''
	def __init__(self, dataset, k=10):
		super(Evaluator, self).__init__()
		self.instances = []
		self.dataset = dataset
		self.k = k
	
	def add_instance(self, goal, predictions):
		self.instances.append([goal, predictions])

	def _load_interaction_matrix(self):
		'''Load the training set as an interaction matrix between items and users in a sparse format.
		'''
		filename = self.dataset.dirname + 'data/train_set_triplets'
		if os.path.isfile(filename + '.npy'):
			file_content = np.load(filename + '.npy')
		else:
			file_content = np.loadtxt(filename)
			np.save(filename, file_content)

		self._interactions = ssp.coo_matrix((np.ones(file_content.shape[0]), (file_content[:,1], file_content[:,0]))).tocsr()

	def _intra_list_similarity(self, items):
		'''Compute the intra-list similarity of a list of items.
		'''
		if not hasattr(self, "_interactions"):
			self._load_interaction_matrix()

		norm = np.sqrt(np.asarray(self._interactions[items, :].sum(axis=1)).ravel())
		sims = self._interactions[items, :].dot(self._interactions[items, :].T).toarray()
		S = 0
		for i in range(len(items)):
			for j in range(i):
				S += sims[i, j] / norm[i] / norm[j]

		return S

	def average_intra_list_similarity(self):
		'''Return the average intra-list similarity, as defined in "Auralist: Introducing Serendipity into Music Recommendation"
		'''

		ILS = 0
		for goal, prediction in self.instances:
			if len(prediction) > 0:
				ILS += self._intra_list_similarity(prediction[:min(len(prediction), self.k)])

		return ILS / len(self.instances)


	def success_in_top_items(self):
		'''Return the percentage of correct long term predictions that are about items in the top 1% of the most popular items.
		'''

		correct_predictions = self.get_correct_predictions()
		nb_pop_items = self.dataset.n_items // 100
		pop_items = np.argpartition(-self.dataset.item_popularity, nb_pop_items)[:nb_pop_items]

		return len([i for i in correct_predictions if i in pop_items])/len(correct_predictions)

	def average_novelty(self):
		'''Return the average novelty measure, as defined in "Auralist: Introducing Serendipity into Music Recommendation"
		'''

		nb_of_ratings = sum(self.dataset.item_popularity)

		novelty = 0
		for goal, prediction in self.instances:
			if len(prediction) > 0:
				novelty += sum(map(np.log2, self.dataset.item_popularity[prediction[:min(len(prediction), self.k)]] / nb_of_ratings)) / min(len(prediction), self.k)

		return -novelty / len(self.instances)

	def average_precision(self):
		'''Return the average number of correct predictions per instance.
		'''
		precision = 0
		for goal, prediction in self.instances:
			if len(prediction) > 0:
				precision += float(len(set(goal) & set(prediction[:min(len(prediction), self.k)]))) / min(len(prediction), self.k)

		return precision / len(self.instances)

	def average_recall(self):
		'''Return the average recall.
		'''
		recall = 0
		for goal, prediction in self.instances:
			if len(goal) > 0:
				recall += float(len(set(goal) & set(prediction[:min(len(prediction), self.k)]))) / len(goal)

		return recall / len(self.instances)

	def average_ndcg(self):
		ndcg = 0.
		for goal, prediction in self.instances:
			if len(prediction) > 0:
				dcg = 0.
				max_dcg = 0.
				for i, p in enumerate(prediction[:min(len(prediction), self.k)]):
					if i < len(goal):
						max_dcg += 1. / np.log2(2 + i)

					if p in goal:
						dcg += 1. / np.log2(2 + i)

				ndcg += dcg/max_dcg

		return ndcg / len(self.instances)

	def strict_success_percentage(self):
		'''Return the percentage of instances for which the first goal was in the predictions
		'''
		score = 0
		for goal, prediction in self.instances:
			score += int(goal[0] in prediction[:min(len(prediction), self.k)])

		return score / len(self.instances)

	def general_success_percentage(self):
		'''Return the percentage of instances for which at least one of the goals was in the predictions
		'''
		score = 0
		for goal, prediction in self.instances:
			score += int(len(set(goal) & set(prediction[:min(len(prediction), self.k)])) > 0)

		return score / len(self.instances)

	def get_all_goals(self):
		'''Return a concatenation of the goals of each instances
		'''
		return [g for goal, _ in self.instances for g in goal]

	def get_strict_goals(self):
		'''Return a concatenation of the strict goals (i.e. the first goal) of each instances
		'''
		return [goal[0] for goal, _ in self.instances]

	def get_all_predictions(self):
		'''Return a concatenation of the predictions of each instances
		'''
		return [p for _, prediction in self.instances for p in prediction[:min(len(prediction), self.k)]]

	def get_correct_predictions(self):
		'''Return a concatenation of the correct predictions of each instances
		'''
		correct_predictions = []
		for goal, prediction in self.instances:
			correct_predictions.extend(list(set(goal) & set(prediction[:min(len(prediction), self.k)])))
		return correct_predictions

	def get_correct_strict_predictions(self):
		'''Return a concatenation of the strictly correct predictions of each instances (i.e. predicted the first goal)
		'''
		correct_predictions = []
		for goal, prediction in self.instances:
			correct_predictions.extend(list(set([goal[0]]) & set(prediction[:min(len(prediction), self.k)])))
		return correct_predictions

	def get_rank_comparison(self):
		'''Returns a list of tuple of the form (position of the item in the list of goals, position of the item in the recommendations)
		'''
		all_positions = []
		for goal, prediction in self.instances:
			position_in_predictions = np.argsort(prediction)[goal]
			all_positions.extend(list(enumerate(position_in_predictions)))

		return all_positions

class DistributionCharacteristics(object):
	"""DistributionCharacteristics computes and plot certain characteristics of a list of movies, such as the distribution of popularity.
	"""
	def __init__(self, movies):
		super(DistributionCharacteristics, self).__init__()
		self.movies = collections.Counter(movies)

	def plot_frequency_distribution(self):
		'''Plot the number of items versus the frequency
		'''
		frequencies = self.movies.values()
		freq_distribution = collections.Counter(frequencies)
		#plt.figure()
		#plt.loglog(freq_distribution.keys(), freq_distribution.values(), '.')
		#plt.show()

	def number_of_movies(self):
		return len(self.movies)

		