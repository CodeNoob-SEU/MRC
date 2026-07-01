/********************************************************************
************************************************/

#ifndef __LIBDXCAP_DATASTRU__20110805__
#define __LIBDXCAP_DATASTRU__20110805__
#include <string>

typedef void* device_handle;
typedef void* image_handle;
typedef void* dxmp4_handle;
typedef void* scale_handle;

#define   WM_SAMPLER_CHANGED     ( WM_APP+100 )
#define   WM_PREVIEW_UPDATE      ( WM_APP+1000 )
#define   WM_WEBRTC_MSG          ( WM_APP+1001 )

// 视频颜色空间
enum {cs_rgb24, cs_rgb32, cs_yuy2};
enum { dp_overlay, dp_vmr9, dp_d3d, dp_offscreen, dp_sdl };

// 设备信息
#define MAX_DEVICE_NAME		128
typedef struct _device_tag
{
	unsigned	idx;							// 过滤器在枚举过程中的序号
	char		deviceName[MAX_DEVICE_NAME];	// 过滤器的名称
} DEVICE_TAG, *PDEVICE_TAG;

typedef struct _videocaps
{
	int width;
	int height;
}VIDEOCAPS, *PVIDEOCAPS;

//----视频编码参数申明----------------------
#define INTEL264CODEC_FILTER "intelH264 Codec\0"
#define X264CODEC_FILTER "x264 Codec\0"
#define XVIDCODEC_FILTER "xvid Codec\0"
#define NVIDIACODEC_FILTER "nvidia Codec\0"
#define INTELHEVCCODEC_FILTER "intel HEVC Codec\0"
#define NVIDIAHEVCCODEC_FILTER "nvidia HEVC Codec\0"

#define AAC_FILTER       "aac Codec\0"
#define SYS_FILTER       "sys Codec\0"

enum {codec_sys, codec_intel264, codec_x264, codec_xvid, codec_nvidia, codec_intelHEVC, codec_nvidiaHEVC };
enum {acodec_sys, acodec_aac};
enum {codec_CBR=0, codec_VBR=1};
typedef struct{
	int fps;    //帧率
	int keyframeinterval;  //关键帧间隔，必须大于等于帧率
	int rcMode;   //码率控制:codec_CBR(平均码率)/codec_VBR(恒定质量)；
	int Quality; //codec_VBR: 0 ~ 51 (默认值为32)，值越大效果越差文件越少
	int Bitrate; //codec_CBR，码率（单位：kbps）默认值256，x264中为0时，编码器内部自己计算

	int Maxrbps;  //codec_CBR有效，默认值4000,位率范围:56bps ~ 10Mbps; 单位Kbps
	int Peekbps;  //codec_CBR有效，默认值1000bps,位率范围:56bps ~ 10Mbps; 单位Kbps
}VidCodecPara;
//-------------------------------------------

enum{FILE_AVI=1, FILE_MP4=2};

enum {drate_color};
typedef struct{
	int nBrightness; // 亮度，取值(-255到255)
	int nContrast;  //对比度，取值(-100到100)
}DRateColorPara;

enum VidScaleAlogrithm
{
	VID_SCALE_POINT	= 0,
	VID_SCALE_BILINEAR,
	VID_SCALE_BICUBIC
};



//----网络传输参数----------------------
enum 
{ 
	net_crtsp	= 0x0001, 
	net_crtmp	= 0x0002, 
	net_srt		= 0x0004, 
	net_webrtc	= 0x0008, 
	net_all		= 0xffff 
};
enum {data_vid, data_aud};
typedef struct{
	char  srt_uri[MAX_PATH];  //srt地址
	short port;//rtsp服务器监听端口(默认为554)
	char  crtmp_uri[MAX_PATH];  //rtmp地址
	short rtcPort; //webrtc服务器监听端口（默认为8888）;
	char rtcPeerName[32]; //webrtc端名称（默认为zhongan）;
	char rtcRoomId[16];
	bool bUseWebrtcCodec;
	char STUN[256];
}NetTransPara,*PNetTransPara;

struct ZAMSG
{
	int nMsgId;
	int nPeerId;
	char strMsg[65536];
};
//-------------------------------------------

enum {style_solid, style_dash, style_dot, style_dashdot};

enum {PropertyPage_VideoCapureFilter, PropertyPage_VideoCapurePin, PropertyPage_VideoCrossbar};

typedef struct {
	int x, y; // 坐标
	int picOpacity; // 图片透明度（0 ~ 255），255不透明
	const char *picFileName; // 叠加图片路径
	const char *itemText; // 叠加文字(叠加图片路径为NULL时有效，否则无效)
	const char *textFaceName; // 字体名
	int textPointSize; // 文字大小
	BOOL textTransparent; // 文字是否透明
	COLORREF textColor; // 字体颜色
	COLORREF textBgcolor; // 字体背景色(文字不透明时有效，否则无效)
}MP4LaunchImage, *PMP4LaunchImage;

typedef struct {
	const char *mp4_filename; // 需要裁剪的MP4文件
	_int64 time_begin; // 起始时间，单位毫秒(ms)
	_int64 time_end; // 结束时间，单位毫秒(ms)
	PMP4LaunchImage launch_img; // 片头叠加的图片或文字数组
	int launch_img_num; // 片头叠加的图片或文字数组大小
	int launch_img_time; // 片头显示的时间，单位毫秒(ms)
}MP4FileSlice, *PMP4FileSlice;

enum {ahd_eqgain_1, ahd_eqgain_2};

typedef struct
{
	unsigned long textColor;
	int left;
	int right;
	int top;
	int bottom;
	float pro;//检测框概率值
}AIExamResult;

typedef void* DCM_HANDLE;
typedef void* SERIES_HANDLE;

enum RGBTYPE
{
	RGB24,
	RGBA
};

enum {
	DICOM_QUERY_LEVEL_PATIENT = 0,
	DICOM_QUERY_LEVEL_STUDY = 1,
	DICOM_QUERY_LEVEL_SERIES = 2,
	DICOM_QUERY_LEVEL_IMAGE = 3,
};

typedef int(__stdcall *LoadStatusFunc)(DCM_HANDLE* pDCMHandel, const char* chClientApplicationTitle, float fDownloadPercent, const char* chCurFileName, float fCurFileDownloadPercent, void* pContext);
typedef int(__stdcall *Mp42DcmStatusFunc)(const char* chMp4FileName, float fConvertPercent, void* pContext);
#endif // __LIBDXCAP_DATASTRU__20110805__