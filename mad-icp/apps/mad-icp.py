# Copyright 2024 R(obots) V(ision) and P(erception) group
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from pathlib import Path
import typer
from typing_extensions import Annotated
from rich.progress import track
from rich.console import Console
from enum import Enum
import os, sys, yaml
import numpy as np
from datetime import datetime
from utils.utils import write_transformed_pose
from utils.ros_reader import Ros1Reader
from utils.kitti_reader import KittiReader

sys.path.append("../build/src/odometry/")
# binded odometry
from pypeline import Pipeline, VectorEigen3d


console = Console()

class InputDataInterface(str, Enum):
    kitti = "kitti",
    ros1  = "ros1",
    # Can insert additional conversion formats

InputDataInterface_lut = {
    InputDataInterface.kitti: KittiReader,
		InputDataInterface.ros1: Ros1Reader
}

def main(data_path: Annotated[
    Path, typer.Option(help="path containing one or more rosbags (folder path)", show_default=False)],
				 estimate_path: Annotated[
    Path, typer.Option(help="trajectory estimate output path (folder path)", show_default=False)],
				 dataset_config: Annotated[
    Path, typer.Option(help="dataset configuration file", show_default=False)],
				 mad_icp_config: Annotated[
    Path, typer.Option(help="parameters for mad icp", show_default=True)] = "../configurations/params.cfg", 
				 num_cores: Annotated[
    int, typer.Option(help="how many threads to use for icp (suggest maximum num)", show_default=True)] = 4, 
				 num_keyframes: Annotated[
    int, typer.Option(help="max number of kf kept in the local map (suggest as num threads)", show_default=True)] = 4, 
				 realtime: Annotated[
    bool, typer.Option(help="if true anytime realtime", show_default=True)] = False) -> None:
	
	if not data_path.is_dir() or not estimate_path.is_dir() or not dataset_config.is_file():
		console.print("[red] input dir or file are not correct")
		sys.exit(-1)
	
	reader_type = InputDataInterface.kitti
	if "bag" in data_path.glob("*.bag").__next__().suffix:
		console.print("[yellow] the dataset is in rosbag format")
		reader_type = InputDataInterface.ros1
	else:
		console.print("[yellow] the dataset is in kitti format")

	console.print("[green] parsing dataset configuration file")
	data_config_file = open(dataset_config, 'r')
	data_cf = yaml.safe_load(data_config_file)
	min_range = data_cf["min_range"] 
	max_range = data_cf["max_range"] 
	sensor_hz = data_cf["sensor_hz"] 
	deskew = data_cf["deskew"]
	topic = None
	if reader_type ==  InputDataInterface.ros1 :
		topic = data_cf["rosbag_topic"]
	lidar_to_base = np.array(data_cf["lidar_to_base"])

	console.print("[green] parsing mad-icp configuration file")
	mad_icp_config_file = open(mad_icp_config, 'r')
	mad_icp_cf = yaml.safe_load(mad_icp_config_file)
	b_max = mad_icp_cf["b_max"]
	b_min = mad_icp_cf["b_min"]
	b_ratio = mad_icp_cf["b_ratio"]
	p_th = mad_icp_cf["p_th"]
	rho_ker = mad_icp_cf["rho_ker"]
	n = mad_icp_cf["n"]

	# check some params for machine
	if(realtime and num_keyframes > num_cores):
		console.print("[red] if you chose realtime option, we suggest to chose a num_cores at least >= than the num_keyframes")
		sys.exit(-1)

	console.print("[green] setting up pipeline for odometry estimation")
	pipeline = Pipeline(sensor_hz, deskew, b_max, rho_ker, p_th, b_min, b_ratio, num_keyframes, num_cores, realtime)

	estimate_file_name = estimate_path / "estimate.txt"
	estimate_file = open(estimate_file_name, 'w')

	with InputDataInterface_lut[reader_type](data_path, min_range, max_range, topic, sensor_hz) as reader:
		for ts, points in track(reader, description="processing..."):

      # print("Loading frame #", pipeline.currentID())
			t_start = datetime.now()
			points = VectorEigen3d(points)
			pipeline.compute(ts, points)
			t_end = datetime.now()
			t_delta = t_end - t_start
			print("time for odometry estimation in ms: ", t_delta.total_seconds() * 1000, "\n")

			lidar_to_world = pipeline.currentPose()
			write_transformed_pose(estimate_file, lidar_to_world, lidar_to_base)

	estimate_file.close()


if __name__ == '__main__':
	typer.run(main)