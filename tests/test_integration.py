#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
These tests check that the server can handle different experiments
(multi/single stimuli, multi/single outcome). They ensure that the
data is correctly stored in the database tables (raw, param, and outcome).
It also checks that the experiment table is correctly populated
(generate_experiment_table method).
"""

import json
import logging
import unittest
import uuid
from unittest.mock import call, MagicMock, patch, PropertyMock

import aepsych.server as server
import aepsych.utils_logging as utils_logging
import torch
from aepsych.config import Config

class IntegrationTestCase(unittest.TestCase):
    def setUp(self):
        # setup logger
        server.logger = utils_logging.getLogger(logging.DEBUG, "logs")

        # random port
        socket = server.sockets.PySocket(port=0)

        # random datebase path name without dashes
        database_path = "./{}.db".format(str(uuid.uuid4().hex))
        self.s = server.AEPsychServer(socket=socket, database_path=database_path)

        # Server messages
        self.setup_request = {
            "type": "setup",
            "version": "0.01",
            "message": {"config_str": None},
        }
        self.ask_request = {"type": "ask", "message": ""}
        self.tell_request = {
            "type": "tell",
            "message": {"config": {}, "outcome": 0},
            "extra_info": {},
        }

    def tearDown(self):
        self.s.cleanup()

        # cleanup the db
        if self.s.db is not None:
            self.s.db.delete_db()

    def get_tell(self, x1, x2, outcomes):
        self.tell_request["message"]["config"]["x1"] = x1
        self.tell_request["message"]["config"]["x2"] = x2
        self.tell_request["message"]["outcome"] = outcomes
        self.tell_request["extra_info"]["e1"] = 1
        self.tell_request["extra_info"]["e2"] = 2

    def check_multi_stimuli(self, x1, x2):
        x1_stimuli0_saved = self.s.db.get_engine().execute("SELECT x1_stimuli0 FROM experiment_table").fetchall()
        x1_stimuli1_saved = self.s.db.get_engine().execute("SELECT x1_stimuli1 FROM experiment_table").fetchall()
        x1_stimuli0_saved = [item for sublist in x1_stimuli0_saved for item in sublist]
        x1_stimuli1_saved = [item for sublist in x1_stimuli1_saved for item in sublist]

        # Reshape
        x1_saved = []
        for i in range(len(x1_stimuli0_saved)):
            x1_saved.append([x1_stimuli0_saved[i], x1_stimuli1_saved[i]])
        self.assertEqual(x1_saved, x1)

        x2_stimuli0_saved = self.s.db.get_engine().execute("SELECT x2_stimuli0 FROM experiment_table").fetchall()
        x2_stimuli1_saved = self.s.db.get_engine().execute("SELECT x2_stimuli1 FROM experiment_table").fetchall()
        x2_stimuli0_saved = [item for sublist in x2_stimuli0_saved for item in sublist]
        x2_stimuli1_saved = [item for sublist in x2_stimuli1_saved for item in sublist]

        # Reshape
        x2_saved = []
        for i in range(len(x2_stimuli0_saved)):
            x2_saved.append([x2_stimuli0_saved[i], x2_stimuli1_saved[i]])
        self.assertEqual(x2_saved, x2)

    def check_single_stimuli(self, x1, x2):
        x1_saved = self.s.db.get_engine().execute("SELECT x1 FROM experiment_table").fetchall()
        x1_saved = [item for sublist in x1_saved for item in sublist]
        self.assertTrue(x1_saved == x1)

        x2_saved = self.s.db.get_engine().execute("SELECT x2 FROM experiment_table").fetchall()
        x2_saved = [item for sublist in x2_saved for item in sublist]
        self.assertTrue(x2_saved == x2)

    def check_multi_outcome(self, outcomes):
        outcome1_saved = self.s.db.get_engine().execute("SELECT outcome_0 FROM experiment_table").fetchall()
        outcome2_saved = self.s.db.get_engine().execute("SELECT outcome_1 FROM experiment_table").fetchall()
        outcome1_saved = [item for sublist in outcome1_saved for item in sublist]
        outcome2_saved = [item for sublist in outcome2_saved for item in sublist]
        outcomes_saved = []
        for i in range(len(outcome1_saved)):
            outcomes_saved.append([outcome1_saved[i], outcome2_saved[i]])
        self.assertEqual(outcomes, outcomes_saved)

    def check_single_outcome(self, outcomes):
        outcomes_saved = self.s.db.get_engine().execute("SELECT outcome FROM experiment_table").fetchall()
        outcomes_saved = [item for sublist in outcomes_saved for item in sublist]
        self.assertTrue(outcomes_saved == outcomes)

    def test_single_stimuli_single_outcome(self):
        """Test a single-stimulus experiment with a single outcome."""
        # Read config from .ini file
        with open('tests/configs/singleStimuli_singleOutcome.ini', 'r') as f:
            dummy_simple_config = f.read()
        self.setup_request["message"]["config_str"] = dummy_simple_config

        self.s.versioned_handler(self.setup_request)

        x1 = [0.1, 0.2, 0.3, 1, 2, 3, 4]
        x2 = [4, 0.1, 3, 0.2, 2, 1, 0.3]
        outcomes = [1, -1, 0.1, 0, -0.1, 0, 0]

        i = 0
        while not self.s.strat.finished:
            self.s.unversioned_handler(self.ask_request)
            self.get_tell([x1[i]], [x2[i]], outcomes[i])
            i = i + 1
            self.s.unversioned_handler(self.tell_request)

        # Experiment id
        exp_id = self.s.db.get_master_records()[0].experiment_id

        # Get tables data
        raw_data = self.s.db.get_raw_for(exp_id)
        param_data = self.s.db.get_all_params_for(master_id=exp_id)
        outcome_data = self.s.db.get_all_outcomes_for(master_id=exp_id)

        # Create table with experiment data
        self.s.generate_experiment_table(exp_id, return_df=False)

        # Check that table exists
        self.assertTrue('experiment_table' in self.s.db.get_engine().table_names())

        # Check that parameter and outcomes values are correct
        self.check_single_stimuli(x1, x2)
        self.check_single_outcome(outcomes)


    def test_multi_stimuli_multi_outcome(self):
        """Test a multi-stimulus experiment with a multiple outcomes."""
        # Read config from .ini file
        with open('tests/configs/multiStimuli_multiOutcome.ini', 'r') as f:
            dummy_pairwise_config = f.read()

        self.setup_request["message"]["config_str"] = dummy_pairwise_config
        self.s.versioned_handler(self.setup_request)

        x1 = [[0.1, 0.2], [0.3, 1], [2, 3], [4, 0.1], [0.2, 2], [1, 0.3], [0.3, 0.1]]
        x2 = [[4, 0.1], [3, 0.2], [2, 1], [0.3, 0.2], [2, 0.3], [1, 0.1], [0.3, 4]]
        outcomes = [[1, 0], [-1, 0], [0.1, 0], [0, 0], [-0.1, 0], [0, 0], [0, 0]]

        i = 0
        while not self.s.strat.finished:
            self.s.unversioned_handler(self.ask_request)
            self.get_tell(x1[i], x2[i], outcomes[i])
            i = i + 1
            self.s.unversioned_handler(self.tell_request)

        # Experiment id
        exp_id = self.s.db.get_master_records()[0].experiment_id

        # Get tables data
        raw_data = self.s.db.get_raw_for(exp_id)
        param_data = self.s.db.get_all_params_for(master_id=exp_id)
        outcome_data = self.s.db.get_all_outcomes_for(master_id=exp_id)

        # Create table with experiment data
        self.s.generate_experiment_table(exp_id, return_df=False)

        # Check that table exists
        self.assertTrue('experiment_table' in self.s.db.get_engine().table_names())

        # Check that parameter and outcomes values are correct
        self.check_multi_stimuli(x1, x2)
        self.check_multi_outcome(outcomes)

if __name__ == "__main__":
    unittest.main()
