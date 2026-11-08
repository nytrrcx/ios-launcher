ARCHS := arm64
TARGET := iphone:clang:latest:15.0
include $(THEOS)/makefiles/common.mk

LIBRARY_NAME = CAHighFPS
#TWEAK_NAME = CAHighFPS

CAHighFPS_FILES = Tweak.x
CAHighFPS_CFLAGS = -fobjc-arc
CAHighFPS_FRAMEWORKS = UIKit QuartzCore
CAHighFPS_INSTALL_PATH = /Applications/Geode.app/Frameworks

#include $(THEOS_MAKE_PATH)/tweak.mk
include $(THEOS_MAKE_PATH)/library.mk
