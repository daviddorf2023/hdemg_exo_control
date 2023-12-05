import rospy
from std_msgs.msg import Float64
from mobile_hdemg_exo.msg import StampedFloat64MultiArray, StampedFloat64
from mobile_hdemg_exo.utils.moving_average import MovingAverage
from mobile_hdemg_exo.utils.processing import notch_filter, butter_bandpass, csv_output
from mobile_hdemg_exo.processors.emg_process_cst import EMGProcessorCST
import numpy as np
from scipy import signal

while not rospy.get_param("startup_gui_completed"):
    rospy.sleep(0.1)

SAMPLING_FREQUENCY = rospy.get_param("/sampling_frequency", int)
REMOVED_CHANNELS = rospy.get_param("/channels_to_remove")


class EMGProcessorNode:
    """
    A class for processing EMG data.

    Attributes:
        r: A ROS Rate object.
        raw_sub: A ROS subscriber for the /hdEMG_stream_raw topic.
        processed_pub: A ROS publisher for the /hdEMG_stream_processed topic.
        raw_data: A list of integers representing EMG data.
        raw_timestamp: The timestamp of the EMG data.
        moving_avg_object: A MovingAverage object.
        start_time: The time at which the node was started.

    Methods:
        callback: A callback function for the /hdEMG_stream_raw topic.
        process_emg: Processes EMG data.
        notch_filter: Applies a notch filter to the EMG data.
        butter_bandpass: Creates a bandpass filter.
        csv_output: Outputs the EMG reading to a CSV file.
    """

    def __init__(self):
        rospy.init_node('emg_processor_node')
        self.r = rospy.Rate(SAMPLING_FREQUENCY)
        self.start_time = rospy.Time.now()
        self.raw_sub = rospy.Subscriber(
            'hdEMG_stream_raw', StampedFloat64MultiArray, self.callback)
        self.processor = EMGProcessorCST()
        self.rms_pub = rospy.Publisher(
            'hdEMG_stream_rms', StampedFloat64, queue_size=10)
        self.cst_pub = rospy.Publisher(
            'hdEMG_stream_cst', StampedFloat64, queue_size=10)
        self.raw_data = None
        self.rms_mov_avg = MovingAverage(
            window_size=5*SAMPLING_FREQUENCY)  # 5 seconds
        self.cst_mov_avg = MovingAverage(
            window_size=5*SAMPLING_FREQUENCY)  # 5 seconds
        self.b, self.a = butter_bandpass(20, 200, SAMPLING_FREQUENCY, order=2)

    def callback(self, raw_message):
        self.raw_data = raw_message.data.data

    def process_emg(self):
        for channel in REMOVED_CHANNELS:
            hdemg_filtered[channel] = 0
        # RMS
        notch_reading = notch_filter(self.raw_data, SAMPLING_FREQUENCY)
        hdemg_filtered = signal.filtfilt(self.b, self.a, notch_reading)
        rms_emg = (np.mean(np.array(hdemg_filtered)**2))**0.5
        smooth_rms = self.rms_mov_avg.moving_avg(rms_emg)
        rms_message = StampedFloat64()
        rms_message.header.stamp = rospy.Time.now() - self.start_time
        rms_message.data = Float64(data=smooth_rms)
        self.rms_pub.publish(rms_message)
        # CST
        cst_emg = self.processor.process_reading(hdemg_filtered/10)
        smooth_cst = self.cst_mov_avg.moving_avg(cst_emg)
        cst_message = StampedFloat64()
        cst_message.header.stamp = rospy.Time.now() - self.start_time
        cst_message.data = Float64(data=smooth_cst)
        self.cst_pub.publish(cst_message)

        csv_output([smooth_rms, smooth_cst])
        self.r.sleep()


if __name__ == '__main__':
    emg_processor_node = EMGProcessorNode()
    while not rospy.is_shutdown():
        if emg_processor_node.raw_data is not None:
            emg_processor_node.process_emg()