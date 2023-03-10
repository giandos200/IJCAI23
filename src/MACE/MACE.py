import pandas as pd
import numpy as np
import copy

from sklearn.model_selection import train_test_split

import src.MACE.normalizedDistance as normalizedDistance
from src.MACE.modelConversion import *
from src.MACE.utils import *
from pysmt.shortcuts import *
from pysmt.typing import *

from src.MACE.loadData import Dataset
from tqdm import tqdm

VALID_ATTRIBUTE_DATA_TYPES = { \
  'numeric-int', \
  'numeric-real', \
  'binary', \
  'categorical', \
  'sub-categorical', \
  'ordinal', \
  'sub-ordinal'}
VALID_ATTRIBUTE_NODE_TYPES = { \
  'meta', \
  'input', \
  'output'}
VALID_ACTIONABILITY_TYPES = { \
  'none', \
  'any', \
  'same-or-increase', \
  'same-or-decrease'}
VALID_MUTABILITY_TYPES = { \
  True, \
  False}

def getOneHotEquivalent(data_frame_non_hot, attributes_non_hot):

  # TODO: see how we can switch between feature_names = col names for kurz and long (also maybe ordered)

  data_frame = copy.deepcopy(data_frame_non_hot)
  attributes = copy.deepcopy(attributes_non_hot)

  def setOneHotValue(val):
    return np.append(np.append(
      np.zeros(val - 1),
      np.ones(1)),
      np.zeros(num_unique_values - val)
    )

  def setThermoValue(val):
    return np.append(
      np.ones(val),
      np.zeros(num_unique_values - val)
    )

  for col_name in data_frame.columns.values:

    if attributes[col_name].attr_type not in {'categorical', 'ordinal'}:
      continue

    old_col_name_long = col_name
    new_col_names_long = []
    new_col_names_kurz = []

    old_attr_name_long = attributes[old_col_name_long].attr_name_long
    old_attr_name_kurz = attributes[old_col_name_long].attr_name_kurz
    old_attr_type = attributes[old_col_name_long].attr_type
    old_node_type = attributes[old_col_name_long].node_type
    old_actionability = attributes[old_col_name_long].actionability
    old_mutability = attributes[old_col_name_long].mutability
    old_lower_bound = attributes[old_col_name_long].lower_bound
    old_upper_bound = attributes[old_col_name_long].upper_bound

    num_unique_values = int(old_upper_bound - old_lower_bound + 1)

    assert old_col_name_long == old_attr_name_long

    new_attr_type = 'sub-' + old_attr_type
    new_node_type = old_node_type
    new_actionability = old_actionability
    new_mutability = old_mutability
    new_parent_name_long = old_attr_name_long
    new_parent_name_kurz = old_attr_name_kurz


    if attributes[col_name].attr_type == 'categorical': # do not do this for 'binary'!

      new_col_names_long = [f'{old_attr_name_long}_cat_{i}' for i in range(num_unique_values)]
      new_col_names_kurz = [f'{old_attr_name_kurz}_cat_{i}' for i in range(num_unique_values)]
      print(f'Replacing column {col_name} with {{{", ".join(new_col_names_long)}}}')
      tmp = np.array(list(map(setOneHotValue, list(data_frame[col_name].astype(int).values))))
      data_frame_dummies = pd.DataFrame(data=tmp, columns=new_col_names_long)

    elif attributes[col_name].attr_type == 'ordinal':

      new_col_names_long = [f'{old_attr_name_long}_ord_{i}' for i in range(num_unique_values)]
      new_col_names_kurz = [f'{old_attr_name_kurz}_ord_{i}' for i in range(num_unique_values)]
      print(f'Replacing column {col_name} with {{{", ".join(new_col_names_long)}}}')
      tmp = np.array(list(map(setThermoValue, list(data_frame[col_name].astype(int).values))))
      # data_frame_dummies = pd.DataFrame(data=tmp, columns=new_col_names_long)

    # Update data_frame
    data_frame.drop(columns=old_col_name_long,inplace=True)
    # data_frame = pd.concat([data_frame.drop(columns = old_col_name_long), data_frame_dummies], axis=1)
    data_frame = pd.DataFrame(np.hstack([data_frame.values, tmp]),columns = data_frame.columns.to_list()+new_col_names_long)

    # Update attributes
    del attributes[old_col_name_long]
    for col_idx in range(len(new_col_names_long)):
      new_col_name_long = new_col_names_long[col_idx]
      new_col_name_kurz = new_col_names_kurz[col_idx]
      attributes[new_col_name_long] = DatasetAttribute(
        attr_name_long = new_col_name_long,
        attr_name_kurz = new_col_name_kurz,
        attr_type = new_attr_type,
        node_type = new_node_type,
        actionability = new_actionability,
        mutability = new_mutability,
        parent_name_long = new_parent_name_long,
        parent_name_kurz = new_parent_name_kurz,
        lower_bound = data_frame[new_col_name_long].min(),
        upper_bound = data_frame[new_col_name_long].max())

  return data_frame, attributes

class DatasetAttribute(object):

  def __init__(
    self,
    attr_name_long,
    attr_name_kurz,
    attr_type,
    node_type,
    actionability,
    mutability,
    parent_name_long,
    parent_name_kurz,
    lower_bound,
    upper_bound):

    if attr_type not in VALID_ATTRIBUTE_DATA_TYPES:
      raise Exception("`attr_type` must be one of %r." % VALID_ATTRIBUTE_DATA_TYPES)

    if node_type not in VALID_ATTRIBUTE_NODE_TYPES:
      raise Exception("`node_type` must be one of %r." % VALID_ATTRIBUTE_NODE_TYPES)

    if actionability not in VALID_ACTIONABILITY_TYPES:
      raise Exception("`actionability` must be one of %r." % VALID_ACTIONABILITY_TYPES)

    if mutability not in VALID_MUTABILITY_TYPES:
      raise Exception("`mutability` must be one of %r." % VALID_MUTABILITY_TYPES)

    if lower_bound > upper_bound:
      raise Exception("`lower_bound` must be <= `upper_bound`")

    if attr_type in {'sub-categorical', 'sub-ordinal'}:
      assert parent_name_long != -1, 'Parent ID set for non-hot attribute.'
      assert parent_name_kurz != -1, 'Parent ID set for non-hot attribute.'
      if attr_type == 'sub-categorical':
        assert lower_bound == 0
        assert upper_bound == 1
      if attr_type == 'sub-ordinal':
        # the first elem in thermometer is always on, but the rest may be on or off
        assert lower_bound == 0 or lower_bound == 1
        assert upper_bound == 1
    else:
      assert parent_name_long == -1, 'Parent ID set for non-hot attribute.'
      assert parent_name_kurz == -1, 'Parent ID set for non-hot attribute.'

    if attr_type in {'categorical', 'ordinal'}:
      assert lower_bound == 1 # setOneHotValue & setThermoValue assume this in their logic

    if attr_type in {'binary', 'categorical', 'sub-categorical'}: # not 'ordinal' or 'sub-ordinal'
      # IMPORTANT: surprisingly, it is OK if all sub-ordinal variables share actionability
      #            think about it, if each sub- variable is same-or-increase, along with
      #            the constraints that x0_ord_1 >= x0_ord_2, all variables can only stay
      #            the same or increase. It works :)
      assert actionability in {'none', 'any'}, f"{attr_type}'s actionability can only be in {'none', 'any'}, not `{actionability}`."

    if node_type != 'input':
      assert actionability == 'none', f'{node_type} attribute is not actionable.'
      assert mutability == False, f'{node_type} attribute is not mutable.'

    # We have introduced 3 types of variables: (actionable and mutable, non-actionable but mutable, immutable and non-actionable)
    if actionability != 'none':
      assert mutability == True
    # TODO: above/below seem contradictory... (2020.04.14)
    if mutability == False:
      assert actionability == 'none'

    if parent_name_long == -1 or parent_name_kurz == -1:
      assert parent_name_long == parent_name_kurz == -1

    self.attr_name_long = attr_name_long
    self.attr_name_kurz = attr_name_kurz
    self.attr_type = attr_type
    self.node_type = node_type
    self.actionability = actionability
    self.mutability = mutability
    self.parent_name_long = parent_name_long
    self.parent_name_kurz = parent_name_kurz
    self.lower_bound = lower_bound
    self.upper_bound = upper_bound

class MACE:
    def __init__(self, data, xtrain, model, outcome, numvars, catvars, eps: 1e-3, norm_type='one_norm', random_seed=42):
        self.numvars = numvars
        self.catvars = catvars
        self.epsilon = eps
        self.approach_string = 'MACE'
        self.norm_type = norm_type
        self.SEED = random_seed
        self.model = model
        if isinstance(self.model.steps[1][1], LogisticRegression):
          if isinstance(self.model.steps[1][1].intercept_,float):
            self.model.steps[1][1].intercept_ = np.array([self.model.steps[1][1].intercept_])
        dataset = data.copy()
        self.Cat_Map = {}
        self.l = numvars.copy()
        self.l.extend(catvars.copy())
        dataset = dataset[self.l]
        dataset = pd.concat([outcome, dataset],1)
        numericTransform = self.model.steps[0][1].named_transformers_['num']
        dataset[numericTransform.feature_names_in_] = numericTransform.transform(dataset[numericTransform.feature_names_in_])
        # lenNumvars = self.model.steps[0][1].named_transformers_['num'].feature_names_in_.shape[0]
        # vectorized_sample[:lenNumvars] = numericTransform.transform(vectorized_sample[:lenNumvars].reshape(1, -1))
        for col in self.catvars:
          if dataset[col].nunique() == xtrain[col].nunique():
            continue
          else:
            HundleUknown = set(dataset[col].unique().tolist()).difference(xtrain[col].unique())
            for hU in HundleUknown:
              dataset = dataset[~dataset[col]==hU]
        # [st for st in model.steps[0][1].get_feature_names_out().tolist()]
        for c in catvars:
          self.Cat_Map[c] = {}
          sortUnique = xtrain[c].unique().tolist()
          sortUnique.sort()
          for n,val in enumerate(sortUnique):
            self.Cat_Map[c][val] = n+1
            dataset[c].replace(val,n+1,inplace=True)
        if len(catvars) >0 :
            self.one_hot = True
        else:
          self.one_hot = False

        input_cols, output_col = self.l, outcome.name
        attributes_non_hot = {}
        attributes_non_hot[output_col] = DatasetAttribute(
          attr_name_long=output_col,
          attr_name_kurz='y',
          attr_type='binary',
          node_type='output',
          actionability='none',
          mutability=False,
          parent_name_long=-1,
          parent_name_kurz=-1,
          lower_bound=dataset[output_col].min(),
          upper_bound=dataset[output_col].max())
        for col_idx, col_name in enumerate(input_cols):
          if col_name in numvars:
            # attr_type = 'numeric-real'
            if data[col_name].dtype == int:
              attr_type = 'numeric-int'
            else:
              attr_type = 'numeric-real'
            actionability = 'any'
            mutability = True
          elif col_name in catvars:
            attr_type = 'categorical'
            actionability = 'any'
            mutability = True
          else:
            raise ValueError
          attributes_non_hot[col_name] = DatasetAttribute(
            attr_name_long=col_name,
            attr_name_kurz=f'x{col_idx}',
            attr_type=attr_type,
            node_type='input',
            actionability=actionability,
            mutability=mutability,
            parent_name_long=-1,
            parent_name_kurz=-1,
            lower_bound=dataset[col_name].min(),
            upper_bound=dataset[col_name].max())
        if self.one_hot:
          data_frame, attributes = getOneHotEquivalent(dataset, attributes_non_hot)
        else:
          data_frame, attributes = dataset, attributes_non_hot

        assert model.steps[0][1].get_feature_names_out().tolist().__len__() == data_frame.columns.to_list().__len__()-1
        if self.catvars.__len__()>0:
          assert np.sum(model.steps[0][1].transform(data)[:,len(numvars):] ==  data_frame.values[:,len(numvars)+1:]) ==\
               data_frame.shape[0]*data_frame.values[:, len(numvars)+1:].shape[1], 'columnTransform are not equal'
        self.dataset_obj = Dataset(data_frame, attributes, is_one_hot=self.one_hot, dataset_name=None)
        all_prediction = model.predict(data)
        all_pred_data_df = self.dataset_obj.data_frame_kurz
        self.standard_deviation = list(all_pred_data_df.std())[1:]
        all_pred_data_df['y'] = all_prediction
        numvars_kurz = []
        for n,ncol in enumerate(numvars):
          numvars_kurz.append(f'x{n}')
        all_pred_data_df[numvars_kurz] = model.steps[0][1].transform(data)[:,:len(numvars)]
        self.positive_pred = all_pred_data_df[all_prediction==1]
        self.negative_pred = all_pred_data_df[all_prediction==0]
        self.positive_dict = self.positive_pred.T.to_dict()
        self.negative_dict = self.negative_pred.T.to_dict()


    def generate_counterfactuals(self, sample, total_CFs, desired_class, verbose):
      # samp = np.hstack([sample[self.numvars].values,self.model.steps[0][1].transform(sample)[:, len(self.numvars):]])
      samp = self.model.steps[0][1].transform(sample)
      sample_kurz = pd.DataFrame(samp,columns=self.dataset_obj.getInputAttributeNames('kurz'))
      sample_kurz.index = sample.index
      candidate_factuals = sample_kurz.T.to_dict()
      if desired_class == 0:
        observable_data = self.negative_dict
      else:
        observable_data = self.positive_dict
      for factual_sample_index, factual_sample in candidate_factuals.items():
        factual_sample['y'] = bool(self.model.predict(sample))
        model_symbols = {
          'counterfactual': {},
          'interventional': {},
          'output': {'y': {'symbol': Symbol('y', BOOL)}}
        }
        for attr_name_kurz in self.dataset_obj.getInputAttributeNames('kurz'):
          attr_obj = self.dataset_obj.attributes_kurz[attr_name_kurz]
          lower_bound = attr_obj.lower_bound
          upper_bound = attr_obj.upper_bound
          if attr_name_kurz not in self.dataset_obj.getInputAttributeNames('kurz'):
            continue  # do not overwrite the output
          if attr_obj.attr_type == 'numeric-real':
            model_symbols['counterfactual'][attr_name_kurz] = {
              'symbol': Symbol(attr_name_kurz + '_counterfactual', REAL),
              'lower_bound': Real(float(lower_bound)),
              'upper_bound': Real(float(upper_bound))
            }
            model_symbols['interventional'][attr_name_kurz] = {
              'symbol': Symbol(attr_name_kurz + '_interventional', REAL),
              'lower_bound': Real(float(lower_bound)),
              'upper_bound': Real(float(upper_bound))
            }
          else:  # refer to loadData.VALID_ATTRIBUTE_TYPES
            model_symbols['counterfactual'][attr_name_kurz] = {
              'symbol': Symbol(attr_name_kurz + '_counterfactual', INT),
              'lower_bound': Int(int(lower_bound)),
              'upper_bound': Int(int(upper_bound))
            }
            model_symbols['interventional'][attr_name_kurz] = {
              'symbol': Symbol(attr_name_kurz + '_interventional', INT),
              'lower_bound': Int(int(lower_bound)),
              'upper_bound': Int(int(upper_bound))
            }
      all_counterfactuals, closest_counterfactual_sample, closest_interventional_sample = self.findClosestCounterfactualSample(
        self.model,
        model_symbols,
        self.dataset_obj,
        factual_sample,
        self.norm_type,
        self.approach_string,
        self.epsilon,
        total_CFs
      )

      rows = [tuple(np.array([c_x['counterfactual_sample'][attr_name_kurz] for attr_name_kurz in
                              self.dataset_obj.getInputAttributeNames('kurz')])) for c_x in all_counterfactuals if c_x['counterfactual_distance'] != np.infty]
      CF = np.unique(rows, axis=0)
      #totalCF np.zeros((CF.shape[0], len(self.l)))
      numCF = self.model.steps[0][1].transformers_[0][1].inverse_transform(CF[:,:len(self.numvars)])
      if len(self.catvars)>0:
        catCF = self.model.steps[0][1].transformers_[1][1].inverse_transform(CF[:,len(self.numvars):])
        CF = np.hstack([numCF,catCF])
        CF = pd.DataFrame(CF, columns=self.l)
        return CF[sample.columns]
      else:
        CF = pd.DataFrame(CF, columns=self.l)
        return CF[sample.columns]
      # x = 5


    @staticmethod
    def findClosestCounterfactualSample(model_trained, model_symbols, dataset_obj, factual_sample, norm_type,
                                        approach_string, epsilon, N_CF):

      def getCenterNormThresholdInRange(lower_bound, upper_bound):
        return (lower_bound + upper_bound) / 2

      def assertPrediction(dict_sample, model_trained, dataset_obj):
        vectorized_sample = []
        for attr_name_kurz in dataset_obj.getInputAttributeNames('kurz'):
          vectorized_sample.append(dict_sample[attr_name_kurz])
        vectorized_sample = np.array(vectorized_sample)
        #numericTransform = model_trained.steps[0][1].named_transformers_['num']
        #lenNumvars = model_trained.steps[0][1].named_transformers_['num'].feature_names_in_.shape[0]
        #vectorized_sample[:lenNumvars] = numericTransform.transform(vectorized_sample[:lenNumvars].reshape(1, -1))
        sklearn_prediction = int(model_trained.steps[1][1].predict(vectorized_sample.reshape(1,-1))[0])
        pysmt_prediction = int(dict_sample['y'])
        factual_prediction = int(factual_sample['y'])

        # IMPORTANT: sometimes, MACE does such a good job, that the counterfactual
        #            ends up super close to (if not on) the decision boundary; here
        #            the label is underfined which causes inconsistency errors
        #            between pysmt and sklearn. We skip the assert at such points.
        class_predict_proba = model_trained.steps[1][1].predict_proba(vectorized_sample.reshape(1,-1))[0]
        if np.abs(class_predict_proba[0] - class_predict_proba[1]) < 1e-10:
          return

        assert sklearn_prediction == pysmt_prediction, 'Pysmt prediction does not match sklearn prediction.'
        assert sklearn_prediction != factual_prediction, 'Counterfactual and factual samples have the same prediction.'

      # Convert to pysmt_sample so factual symbols can be used in formulae
      factual_pysmt_sample = getPySMTSampleFromDictSample(factual_sample, dataset_obj)

      norm_lower_bound = 0
      norm_upper_bound = 1
      curr_norm_threshold = getCenterNormThresholdInRange(norm_lower_bound, norm_upper_bound)

      # Get and merge all constraints
      print('Constructing initial formulas: model, counterfactual, distance, plausibility, diversity\t\t', end='')
      model_formula = getModelFormula(model_symbols, model_trained.steps[1][1])
      counterfactual_formula = getCounterfactualFormula(model_symbols, factual_pysmt_sample)
      plausibility_formula = getPlausibilityFormula(model_symbols, dataset_obj, factual_pysmt_sample, approach_string)
      distance_formula = getDistanceFormula(model_symbols, dataset_obj, factual_pysmt_sample, norm_type,
                                            approach_string, curr_norm_threshold)
      diversity_formula = TRUE()  # simply initialize and modify later as new counterfactuals come in
      print('done.')

      #iters = 1
      max_iters = N_CF
      counterfactuals = []  # list of tuples (samples, distances)
      # In case no counterfactuals are found (this could happen for a variety of
      # reasons, perhaps due to non-plausibility), return a template counterfactual
      counterfactuals.append({
        'counterfactual_sample': {},
        'counterfactual_distance': np.infty,
        'interventional_sample': {},
        'interventional_distance': np.infty,
        'time': np.infty,
        'norm_type': norm_type})

      print('Solving (not searching) for closest counterfactual using various distance thresholds...')
      c = 0
      pbar = tqdm(range(max_iters), colour='CYAN')
      for iters in pbar: #while iters < max_iters and norm_upper_bound - norm_lower_bound >= epsilon:
        #print(f"\nIteration step: {iters}")
        if iters >10:
          if 'rows' in locals():
            t_CF = tuple(np.array([counterfactuals[-1]['counterfactual_sample'][attr_name_kurz] for attr_name_kurz in
                                   dataset_obj.getInputAttributeNames('kurz')]))
            if t_CF in rows:
              c+=1
              if c==10:
                pbar.set_postfix_str(s='failing in finding diverse Counterfactuals')
                break
            else:
              rows.append(t_CF)
          else:
            rows = [tuple(np.array([c_x['counterfactual_sample'][attr_name_kurz] for attr_name_kurz in
                                    dataset_obj.getInputAttributeNames('kurz')])) for c_x in counterfactuals if
                    c_x['counterfactual_distance'] != np.infty]
            rows = np.unique(rows, axis=0).tolist()
            rows = [tuple(r) for r in rows]
        if pbar.format_dict['elapsed'] > 100 and iters>10:
          pbar.set_postfix_str(s=f'Time exceded and N_iters: {iters}')
          break
        elif pbar.format_dict['elapsed'] > 200:
          pbar.set_postfix_str(s='Time exceded')
          break
        pbar.set_postfix_str(s=
                             f'testing norm threshold {curr_norm_threshold:.6f} in range [{norm_lower_bound:.6f}, {norm_upper_bound:.6f}]...',refresh=True)
        #iters = iters + 1

        formula = And(  # works for both initial iteration and all subsequent iterations
          model_formula,
          counterfactual_formula,
          plausibility_formula,
          distance_formula,
          diversity_formula,
        )

        solver_name = "z3"
        with Solver(name=solver_name) as solver:
          solver.add_assertion(formula)

          solved = solver.solve()

          if solved:  # joint formula is satisfiable
            model = solver.get_model()
            pbar.set_postfix_str(s='solution exists & found.',refresh=True)
            counterfactual_pysmt_sample = {}
            interventional_pysmt_sample = {}
            for (symbol_key, symbol_value) in model:
              # symbol_key may be 'x#', {'p0#', 'p1#'}, 'w#', or 'y'
              tmp = str(symbol_key)
              if 'counterfactual' in str(symbol_key):
                tmp = tmp[:-15]
                if tmp in dataset_obj.getInputOutputAttributeNames('kurz'):
                  counterfactual_pysmt_sample[tmp] = symbol_value
              elif 'interventional' in str(symbol_key):
                tmp = tmp[:-15]
                if tmp in dataset_obj.getInputOutputAttributeNames('kurz'):
                  interventional_pysmt_sample[tmp] = symbol_value
              elif tmp in dataset_obj.getInputOutputAttributeNames('kurz'):  # for y variable
                counterfactual_pysmt_sample[tmp] = symbol_value
                interventional_pysmt_sample[tmp] = symbol_value

            # Convert back from pysmt_sample to dict_sample to compute distance and save
            counterfactual_sample = getDictSampleFromPySMTSample(
              counterfactual_pysmt_sample,
              dataset_obj)
            interventional_sample = getDictSampleFromPySMTSample(
              interventional_pysmt_sample,
              dataset_obj)

            # Assert samples have correct prediction label according to sklearn model
            assertPrediction(counterfactual_sample, model_trained, dataset_obj)
            # of course, there is no need to assertPrediction on the interventional_sample

            counterfactual_distance = normalizedDistance.getDistanceBetweenSamples(
              factual_sample,
              counterfactual_sample,
              norm_type,
              dataset_obj)
            interventional_distance = normalizedDistance.getDistanceBetweenSamples(
              factual_sample,
              interventional_sample,
              norm_type,
              dataset_obj)

            counterfactuals.append({
              'counterfactual_sample': counterfactual_sample,
              'counterfactual_distance': counterfactual_distance,
              'interventional_sample': interventional_sample,
              'interventional_distance': interventional_distance,
              'norm_type': norm_type})

            # Update diversity and distance formulas now that we have found a solution
            # TODO: I think the line below should be removed, because in successive
            #       reductions of delta, we should be able to re-use previous CFs
            # diversity_formula = And(diversity_formula, getDiversityFormulaUpdate(model))

            # IMPORTANT: something odd happens somtimes if use vanilla binary search;
            #            On the first iteration, with [0, 1] bounds, we may see a CF at
            #            d = 0.22. When we update the bounds to [0, 0.5] bounds,  we
            #            sometimes surprisingly see a new CF at distance 0.24. We optimize
            #            the binary search to solve this.
            norm_lower_bound = norm_lower_bound
            # norm_upper_bound = curr_norm_threshold
            if 'mace' in approach_string.lower():
              norm_upper_bound = float(counterfactual_distance + epsilon / 100)  # not float64
            elif 'mint' in approach_string.lower():
              norm_upper_bound = float(interventional_distance + epsilon / 100)  # not float64
            curr_norm_threshold = getCenterNormThresholdInRange(norm_lower_bound, norm_upper_bound)
            distance_formula = getDistanceFormula(model_symbols, dataset_obj, factual_pysmt_sample, norm_type,
                                                  approach_string, curr_norm_threshold)
            # if norm_upper_bound - norm_lower_bound <= epsilon:
            #   break

          else:  # no solution found in the assigned norm range --> update range and try again
            with Solver(name=solver_name) as neg_solver:
              neg_formula = Not(formula)
              neg_solver.add_assertion(neg_formula)
              neg_solved = neg_solver.solve()
              if neg_solved:
                pbar.set_postfix_str(s='no solution exists.',refresh=True)
                norm_lower_bound = curr_norm_threshold
                norm_upper_bound = norm_upper_bound
                curr_norm_threshold = getCenterNormThresholdInRange(norm_lower_bound, norm_upper_bound)
                distance_formula = getDistanceFormula(model_symbols, dataset_obj, factual_pysmt_sample, norm_type,
                                                      approach_string, curr_norm_threshold)
                #if norm_upper_bound - norm_lower_bound <= epsilon:
                #  break
              else:
                pbar.set_postfix_str(s='no solution found (SMT issue).',refresh=True)
                quit()
                break

      # IMPORTANT: there may be many more at this same distance! OR NONE! (what?? 2020.02.19)
      counterfactuals = sorted(counterfactuals, key=lambda x: x['counterfactual_distance'])
      closest_counterfactual_sample = counterfactuals[0]
      closest_interventional_sample = sorted(counterfactuals, key=lambda x: x['interventional_distance'])[0]

      return counterfactuals, closest_counterfactual_sample, closest_interventional_sample


