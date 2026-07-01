
#ifndef __DXMEDIACAP_2011__
#define __DXMEDIACAP_2011__

#include "datastru.h"
#include <string>

extern "C"
{
//UNICODE
/*
描述：
	初始化 SDK ，必须在调用其他函数之前调用
参数：
	无
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXInitialize();
void __stdcall DXUninitialize();

/*
描述：
	获取初始化成功的设备总数
参数：
	无
返回值：
	匹配的设备总数
// */
unsigned __stdcall DXGetDeviceCount();

/*
描述：
	枚举音视频编码过滤器
参数：
	devTags - [out] 用于返回获得的过滤器的 TAG 的数组
	num - [in/out] 指定 devTags 数组的元素个数，返回时则是实际上获得的过滤器的 TAG 的个数
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnumVideoCodecs(PDEVICE_TAG devTags, unsigned& num);
unsigned __stdcall DXEnumAudioCodecs(PDEVICE_TAG devTags, unsigned& num);

/*
描述：
	枚举视频捕捉设备过滤器
参数：
	devTags - [out] 用于返回获得的过滤器的 TAG 的数组
	num - [in/out] 指定 devTags 数组的元素个数，返回时则是实际上获得的过滤器的 TAG 的个数
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnumVideoDevices(PDEVICE_TAG devTags, unsigned& num);

/*
描述：
	枚举音频捕捉和渲染设备过滤器
参数：
	devTags - [out] 用于返回获得的过滤器的 TAG 的数组
	num - [in/out] 指定 devTags 数组的元素个数，返回时则是实际上获得的过滤器的 TAG 的个数
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnumAudioDevices(PDEVICE_TAG devTags, unsigned& num);
unsigned __stdcall DXEnumSoundDevices(PDEVICE_TAG devTags, unsigned& num);

/*
描述：
	占用采集设备
参数：
	idx - [in] 设备在枚举过程中的序号
	err - [out] 返回错误代码
返回值：
	成功则返回设备句柄，否则返回 NULL。可通过 err 获得错误代码
// */
device_handle __stdcall DXOpenDevice(unsigned idx, unsigned* err = NULL);
void __stdcall DXCloseDevice(device_handle device);

/*
描述：
	获取当前视频设备名称
参数：
	device - [in] 设备句柄
返回值：
	返回设备名称，失败则返回NULL
// */
char* __stdcall DXGetDeviceName(device_handle device);

/*
描述：
	获取当前视频设备是否高清
参数：
	device - [in] 设备句柄
返回值：
	TRUE 高清设备；FALSE 标清设备
// */
BOOL __stdcall DXDeviceIsHD(device_handle device);

/*
描述：
	获取当前视频设备是否UVC设备
参数：
	device - [in] 设备句柄
返回值：
	TRUE UVC设备；FALSE 非UVC设备
// */
BOOL __stdcall DXDeviceIsUVC(device_handle device);

/*
描述：
	将属性页显示在制定窗体的指定区域
参数：
	device - [in] 设备句柄
	attrID - [in] 属性类别
	hOwner - [in] 父窗体的句柄。NULL - 隐藏属性页
	rect - [in] 在父窗体上显示的区域。NULL - 表示父窗体的整个客户区
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXShowDeviceAttr(device_handle device, unsigned attrID, HWND hOwner, RECT* rect);

/*
描述：
	获取视频属性
参数：
	device - [in] 设备句柄
	standard - [out] 视频制式
	colorspace - [out] 色彩空间
	width - [out] 视频宽度（单位：像素）
	height - [out] 视频高度（单位：像素）
	framerate - [out] 视频帧率（单位：帧/秒）
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetVideoPara(device_handle device, unsigned& standard, unsigned& colorspace,
								  unsigned& width, unsigned& height, float& framerate);

/*
描述：
	获取视频属性2
参数：
	device - [in] 设备句柄
	standard - [out] 视频制式
	colorspace - [out] 色彩空间
	width - [out] 视频宽度（单位：像素）
	height - [out] 视频高度（单位：像素）
	framerate - [out] 视频帧率（单位：帧/秒）
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetVideoParaHD(device_handle device, unsigned& colorspace,
								  unsigned& width, unsigned& height, float& framerate);
/*
描述：
	枚举视频输出大小
参数：
	device - [in] 设备句柄
	devTags - [out] 用于返回获得的过滤器的 TAG 的数组
	num - [in/out] 指定 vidCaps 数组的元素个数，返回时则是实际上获得的输出格式 Caps 的个数
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnumVideoCaps(device_handle device, PVIDEOCAPS vidCaps, unsigned& num);

/*
描述：
	设置视频属性
参数：
	device - [in] 设备句柄
	standard - [in] 视频制式
	colorspace - [in] 色彩空间
	width - [in] 视频宽度（单位：像素）
	height - [in] 视频高度（单位：像素）
	framerate - [in] 视频帧率（单位：帧/秒）
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetVideoPara(device_handle device, unsigned standard, unsigned colorspace,
								  unsigned width, unsigned height, float framerate);
/*
描述：
	设置视频属性
参数：
	device - [in] 设备句柄
	colorspace - [in] 色彩空间
	width - [in] 视频宽度（单位：像素）
	height - [in] 视频高度（单位：像素）
	framerate - [in] 视频帧率（单位：帧/秒）
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetVideoParaHD(device_handle device, unsigned colorspace,
								  unsigned width, unsigned height, float framerate);

/*
描述：
	获取显示属性的取值范围、默认值、步长、标志
参数：
	device - [in] 设备句柄
	paraType - [in] 参数类型
					0 - 亮度，1 - 对比度，2 - 饱和度，3 - 色度，4 - 锐度
	pMin - [in] 最小值
	pMax - [in] 最大值
	pSteppingDelta - [in] 步长
	pDefault - [in] 默认值
	pCapsFlags - [in] 自动/手动标志
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetDisplayParaRange(device_handle device, unsigned paraType,
										 long* pMin, long* pMax, long* pSteppingDelta, long* pDefault, long* pCapsFlags);

/*
描述：
	获取显示属性
参数：
	device - [in] 设备句柄
	paraType - [in] 参数类型
					0 - 亮度，1 - 对比度，2 - 饱和度，3 - 色度，4 - 锐度
	value - [out] 参数值
	flag - [out] 自动/手动标志
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetDisplayPara(device_handle device, unsigned paraType, long& value, long& flags);

/*
描述：
	设置显示属性
参数：
	device - [in] 设备句柄
	paraType - [in] 参数类型
					0 - 亮度，1 - 对比度，2 - 饱和度，3 - 色度，4 - 锐度
	value - [in] 参数值
	flag - [in] 自动/手动标志
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetDisplayPara(device_handle device, unsigned paraType, long value, long flags);

/*
描述：
	获取设备当前选择的端子和包含的输入端子
参数：
	device - [in] 设备句柄
	curSource - [out] 当前选择的输入端子的序号，设备为UVC：0为HDMI，1为SDI；2为PATTERN；。NULL - 忽略
	sources - [out] 包含的输入端子的类型数组（比如：S-VIDEO、DV...）。NULL - 忽略
	num - [in/out] 端子数量。NULL - 忽略，此时可获取当前选择的输入端子
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetVideoSources(device_handle device, unsigned* curSourceIndex, unsigned* sources = NULL, unsigned char* num = NULL);

/*
描述：
	获取设备当前选择的端子和包含的输入端子
参数：
	device - [in] 设备句柄
	curSource - [out] 当前选择的输入端子的序号，NULL - 忽略
	sourceNames - [out] 包含的输入端子的类型名字指针数组（指针返回内部字符串地址，不需要为保存字符分配内存），NULL - 忽略
	num - [in/out] 端子数量。NULL - 忽略，此时可获取当前选择的输入端子
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetVideoSourcesEx(device_handle device, unsigned* curSourceIndex, char** sourceNames = NULL, unsigned char* num = NULL);

/*
描述：
	设置设备的输入端子
参数：
	device - [in] 设备句柄；
	source - [in] 当前选择的输入端子的序号，1：AV1 2:AV2 3：SVIDEO，该接口是为了保持旧版本的兼容，建议以接口DXSetVideoSourceEx代替
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetVideoSource(device_handle device, unsigned source);

/*
描述：
	设置设备的输入端子
参数：
	device - [in] 设备句柄；
	sourceIndex - [in] 当前选择的输入端子的数组序号,具体设备类型参见通过DXGetVideoSources获取到的sources数组；
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetVideoSourceEx(device_handle device, unsigned sourceIndex);

/*
描述：
	获取设备的信号状态
参数：
	device - [in] 设备句柄
	signal - [out] 信号状态。0 - 信号丢失；1 - 信号正常
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetSignalPresent(device_handle device, unsigned& signal);

/*
描述：
	控制设备运行状态
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXDeviceRun(device_handle device);
unsigned __stdcall DXDeviceRunEx(device_handle device, bool bRotate90 = false, bool bRight = false);
unsigned __stdcall DXDevicePause(device_handle device);
unsigned __stdcall DXDeviceStop(device_handle device);

/*
描述：
	获取设备运行状态
参数：
	device - [in] 设备句柄
	state - [out] 设备运行状态
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetDeviceState(device_handle device, unsigned& state);

/*
描述：
	将视频显示在指定窗体的矩形区域内
参数：
	device - [in] 设备句柄
	hWnd - [in] 显示视频的窗体句柄。NULL - 停止显示视频
	rect - [in] 视频显示的矩形区域。NULL - 占用整个窗体
	vvmrtype - [in] 视频显示模式，0：dp_overlay为OVERLAY显示:1：dp_vmr9为VMR9显示模式，2：dp_d3d为D3D显示模式/openGL:3：dp_offscreen为Offscreen模式 4:dp_sdl为SDL渲染模式
	返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartPreview(device_handle device, HWND hWnd, PRECT rect, unsigned vmrtype);

/*
描述：
	将矩形区域内的视频显示在指定窗体的矩形区域内
参数：
	device - [in] 设备句柄
	hWnd - [in] 显示视频的窗体句柄。NULL - 停止显示视频
	wndrect - [in] 视频显示的矩形区域。NULL - 占用整个窗体
	srcrect - [in] 矩形区域内的视频。NULL - 整个视频区域
	vvmrtype - [in] 视频显示模式，dp_overlay为OVERLAY显示，dp_vmr9为VMR9显示模式，dp_d3d为D3D显示模式，dp_offscreen为Offscreen模式 dp_sdl为SDL渲染模式
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartPreviewEx(device_handle device, HWND hWnd, LPCRECT wndrect, LPCRECT srcrect, unsigned vmrtype, bool bRotate90 = false, bool bRight = false);

/*
描述：
	停止预览
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopPreview(device_handle device);

/*
描述：
	冻结视频显示部分
参数：
	device - [in] 设备句柄
	bFreeze - [in] TRUE - 冻结显示，FALSE - 解冻显示
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXFreezePreview(device_handle device, BOOL bFreeze);

/*
描述：
	APP视频预览窗口收到WM_PREVIEW_UPDATE消息时更新视频预览，例如解除屏幕锁定后恢复视频显示
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码。
// */
void __stdcall DXUpdatePreview(device_handle device);

/*
描述：
	检查设备是否包含音频
参数：
	device - [in] 设备句柄
	bHasAudio - [out] TRUE - 包含音频，FALSE - 没有音频
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXHasAudio(device_handle device, BOOL& bHasAudio);

/*
描述：
	为设备分配音频采集设备。
		注意：!!! 只能在 state_stopped 状态下调用
参数：
	device - [in] 设备句柄
	bSound - [in] TRUE - 开始声音输出，FALSE - 终止声音输出
	audioDevice - [in] 音频采集设备。NULL - 使用设备自带的音频
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetAudioDevice(device_handle device, PDEVICE_TAG audioDevice = NULL);

/*
描述：
	开始或者终止声音输出。
		注意：!!! 只有开始了声音输出，静音操作、音量调节、录像时包含音频等操作才能成功
参数：
	device - [in] 设备句柄
	bSound - [in] TRUE - 开始声音输出，FALSE - 终止声音输出
	soundDevice - [in] 声音输出设备。NULL - 使用默认设备
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetSoundOut(device_handle device, BOOL bSound/*, PDEVICE_TAG soundDevice = NULL*/);

/*
描述：
	静音操作
参数：
	device - [in] 设备句柄
	bMute - [in] TRUE - 静音，FALSE - 非静音
返回值：
	0 - 成功；失败则返回错误代码，一般失败原因是因为没有开始声音输出
// */
unsigned __stdcall DXEnableMute(device_handle device, BOOL bMute);

/*
描述：
	设置音量和平衡
参数：
	device - [in] 设备句柄
	volume - [in] 音量大小，取值范围(0, 100]
	balance - [in] 左右平衡，取值范围[-10, 10]，负数表示左声道强，正数表述右声道强，0 - 左右平衡
				注意：!!! NULL - 表示不设置平衡
返回值：
	0 - 成功；失败则返回错误代码，一般失败原因是因为没有开始声音输出
// */
unsigned __stdcall DXSetAudioVolume(device_handle device, unsigned char volume, unsigned char* const balance = NULL);

/*
描述：
	获取音量和平衡
参数：
	device - [in] 设备句柄
	volume - [out] 音量大小，取值范围(0, 100]
				注意：!!! NULL - 表示不获取音量
	balance - [out] 左右平衡，取值范围[-10, 10]，负数表示左声道强，正数表述右声道强，0 - 左右平衡
				注意：!!! NULL - 表示不获取平衡
返回值：
	0 - 成功；失败则返回错误代码，一般失败原因是因为没有开始声音输出
// */
unsigned __stdcall DXGetAudioVolume(device_handle device, unsigned char* volume, unsigned char* balance = NULL);

/*
描述：
	检查视频编码器
参数：
	codecType--[in]编码器的类型,如:codec_intel264
返回值：
	TRUE - 成功（支持）；FALSE 失败
// */
BOOL __stdcall DXVideoCodecIsSupport(unsigned codecType);

/*
描述：
	检查视频编码器
参数：
	codecFilter--[in]编码器的名称,如:INTEL264CODEC_FILTER
返回值：
	TRUE - 成功（支持）；FALSE 失败
// */
BOOL __stdcall DXVideoCodecFilterIsSupport(const char* codecFilter);

/*
描述：
	更换视频编码器
		注意：!!! 当正在进行录像时，则操作失败
参数：
	device - [in] 设备句柄
	videoEncoder - [in] 视频编码器的 TAG，NULL - 表示不用编码，即录像时采用原始数据
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetVideoCodec(device_handle device, PDEVICE_TAG videoEncoder);

/*
描述：
	设置视频编码器的具体属性（改变编码器类型的时候需调用此函数，因为默认值会导致录像不正常）
参数：
	device - [in] 设备句柄
	codecType--[in]编码器的类型,如:codec_intel264
	pPara - [in]编码器的具体属性（codec_intel264,codec_x264,codec_xvid的属性数组目前都用VidCodecX264Para），NULL - 表示使用默认属性
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetVideoCodecPara(device_handle device, unsigned codecType, void* pPara);
/*
描述：
	获取视频编码器的具体属性
参数：
	device - [in] 设备句柄
	codecType--[out]编码器的类型,如:codec_x264
	pPara - [out]编码器的具体属性
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetVideoCodecPara(device_handle device, unsigned& codecType, void* pPara);

/*
描述：
	更换音频编码器
		注意：!!! 当正在进行录像时，则操作失败
参数：
	device - [in] 设备句柄
	audioEncoder - [in] 音频编码器的 TAG，NULL - 表示不用编码，即录像时采用原始数据
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetAudioCodec(device_handle device, PDEVICE_TAG audioEncoder);

/*
描述：
	开始录像，支持录像成文件，也支持网传
参数：
	device - [in] 设备句柄
	szFileName - [in] 指定录像文件全路径(x264保存为mp4格式的)。NULL - 停止录像
	saveAudio - [in] 是否将音频也录制到文件中
	Reserved0 - [in] 该参数保留
	Reserved1 - [in] 该参数保留
	vidRatio - [in] 视频帧在录像中保存的比例，1为全保存；2为保存1/2；3为保存1/3；4为保存1/4；其他值表示全部保存，此功能只有x264 Codec和xvid Codec才有效果
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartCapture(device_handle device, char* szFileName, BOOL saveAudio,
										  unsigned* Reserved0 = NULL, unsigned* Reserved1 = NULL,unsigned vidRatio=1);

/*
描述：
	开始录像，支持录像文件MP4或AVI
参数：
	fileFormat - [in] 指定录像文件格式，FILE_AVI avi文件；FILE_MP4 MP4文件。
	rct - [in] 限定录像帧的区域，NULL - 不限制
	其他参数与DXStartCapture函数相同。
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartCaptureEx(device_handle device, char* szFileName, BOOL saveAudio, int fileFormat, RECT *rct = NULL,
											unsigned* Reserved0 = NULL, unsigned* Reserved1 = NULL,unsigned vidRatio=1);

/*
描述：
	停止录像
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopCapture(device_handle device);

/*
描述：
	冻结录像部分（包括视频和音频）
	注意：!!! 适用于需要多段时间录像的情况
参数：
	device - [in] 设备句柄
	bFreeze - [in] TRUE - 冻结录像，FALSE - 解冻录像
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXFreezeCaputre(device_handle device, BOOL bFreeze);

/*
描述：
	开始编码音视频数据流
参数：
	device - [in] 设备句柄
	saveAudio - [in] 是否将音频也录制到文件中
	vidRatio - [in] 视频帧在录像中保存的比例，1为全保存；2为保存1/2；3为保存1/3；4为保存1/4；其他值表示全部保存
返回值：
	0 - 成功；失败则返回错误代码。调用此接口后，如果要调用DXStartCapture或者DXStartCaptureQY，需要先调用DXStopCapture；结束编码数据流请调用DXStopCapture
// */
unsigned __stdcall DXStartEncVideo(device_handle device, BOOL saveAudio, unsigned vidRatio=1);


/*
描述：
	开始编码音视频数据流
参数：
	device - [in] 设备句柄
	saveAudio - [in] 是否将音频也录制到文件中
	rct - [in] 限定视频帧的区域，NULL - 不限制
	vidRatio - [in] 视频帧在录像中保存的比例，1为全保存；2为保存1/2；3为保存1/3；4为保存1/4；其他值表示全部保存
返回值：
	0 - 成功；失败则返回错误代码。
// */
unsigned __stdcall DXStartEncVideoEx(device_handle device, BOOL saveAudio, RECT *rct, unsigned vidRatio=1);

/*
描述：
	创建MP4文件
参数：
	device - [in] 设备句柄
	szFileName - [in] mp4文件名
返回值：
	0 - 成功；失败则返回错误代码。
// */
unsigned __stdcall DXCreateMp4file(device_handle device, char* szFileName,bool bHasAud);

/*
描述：
	写压缩数据流到MP4文件中
参数：
	mp4hnd - [in] 文件句柄
	pIn - [in] 数据流
	nlen - [in] 数据流大小
	isKey - [in] 数据流关键帧
	TimeStamp - [in] 数据流时间戳
返回值：
	0 - 成功；否则失败
// */
unsigned __stdcall DXWriteMp4file(dxmp4_handle mp4hnd,int DataType, BYTE * pIn, int nlen, bool isKey, LONGLONG  TimeStamp);

/*
描述：
	关闭MP4文件
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；否则失败
// */
unsigned __stdcall DXCloseMp4file(device_handle device);

/*
描述：
	获取MP4文件信息
参数：
	szFileName - [in] mp4文件路径
	duration - [out] 视频时长（单位：毫秒）
	width - [out] 视频宽度（单位：像素）
	height - [out] 视频高度（单位：像素）
	framerate - [out] 视频帧率（单位：帧/秒）
	bHasAudio - [out] 是否有音频
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetMp4fileInfo(const char *szFileName, unsigned& duration, unsigned& width, unsigned& height, float& framerate, BOOL &bHasAudio);

/*
描述：
	MP4文件录像时增加修复支持，必须在录像开始前设置
参数：
	bSupport - [in] ture - 支持修复；false - 不支持修复，将无法恢复录像异常的mp4文件
返回值：
	0 - 成功；否则失败
// */
void __stdcall DXMp4fileRepairSupport(bool bRepairSupport);

/*
描述：
	修复异常的MP4文件，只有启用了添加录像修复信息生成的文件才能生效
	为避免耗时等待，该接口返回成功时通过接口DXMp4fileRepairProgress查询实际的修复进度
参数：
	szFileName - [in] 需要修复的mp4文件路径
	szSaveName - [in] 保存修复后的mp4文件路径
返回值：
	0 - 成功；否则失败
// */
unsigned __stdcall DXMp4fileRepair(const char *szFileName, char* szSaveName);

/*
描述：
	获取修复MP4文件进度
参数：
	无
返回值：
	（0~100）修复进度，=100表示修复成功完成；-1 失败
// */
int __stdcall DXMp4fileRepairProgress(void);

/*
描述：
	MP4裁剪合并
参数：
	szSaveName - [in] 保存合并的mp4文件路径
	saveAudio - [in] 是否保存音频
	pSlice - [in] 需要裁剪的片段数组指针
	num - [in] 需要裁剪的片段数量
返回值：
	0 - 成功；否则失败
// */
int __stdcall DXMp4fileMerge(const char *szSaveName, BOOL saveAudio, PMP4FileSlice pSlice, int num);

/*
描述：
	获取合并MP4文件进度
参数：
	无
返回值：
	（0~100）合并进度，=100表示修复合并完成；-1 失败
// */
int __stdcall DXMp4fileMergeProgress(void);

/*
描述：
	视频强制编码一个关键帧
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码。
// */
unsigned __stdcall DXNextFrameEncIDR(device_handle device);

/*
描述： 
	编码视频数据回调的函数原型
参数：
	buffer - [out] 缓冲区指针
	bufferSize - [out] 获取的编码数据的缓冲区大小（单位：字节）
	bIsKey - [out] 帧类型
	nTmStamp - [out] 时间戳
	hmp4 - [out]写文件句柄
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
typedef unsigned (__stdcall *fnEncVideoCallback)(unsigned char* buffer, 
	unsigned bufferSize,bool bIsKey, LONGLONG nTmStamp,dxmp4_handle hmp4, void* context);

/*
描述：
	设置编码视频数据回调的函数
参数：
	device - [in] 设备句柄
	fn - [in] 回调函数指针，NULL - 停止回调
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartEncVideoCallback(device_handle device, fnEncVideoCallback fn, void* context);

/*
描述：
	停止编码视频数据回调的函数
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopEncVideoCallback(device_handle device);

/*
描述：
	编码音频数据回调的函数原型
参数：
	buffer - [in] 缓冲区指针
	bufferSize - [out] 获取的编码数据的缓冲区大小（单位：字节）
	nTmStamp - [out] 时间戳
	hmp4 - [out]写文件句柄
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
typedef unsigned (__stdcall *fnEncAudioCallback)(unsigned char* buffer, 
	unsigned bufferSize, LONGLONG nTmStamp,dxmp4_handle hmp4, void* context);

/*
描述：
	设置编码音频数据回调的函数
参数：
	device - [in] 设备句柄
	fn - [in] 回调函数指针，NULL - 停止回调
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartEncAudioCallback(device_handle device, fnEncAudioCallback fn, void* context);
/*
描述：
	停止编码音频数据回调的函数
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopEncAudioCallback(device_handle device);

/*
描述：
	使能去隔行功能
参数：
	device - [in] 设备句柄
	deinterlace - [in] 去隔行化方法：     0 -- SimpleBob
//                                        1 -- TomsMoComp
//                                        2 -- ABCD
//                                        其他值表示自动取消隔行功能
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnableDeinterlace(device_handle device, unsigned deinterlace);

/*
描述：
	使能去噪功能
参数：
	device - [in] 设备句柄
	denoise - [in] 降噪标准 (5 - 100)，其他值表示自动取消去噪功能
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnableDenoise(device_handle device, unsigned denoise = 35);

/*
描述：
	锐化处理功能
参数：
	device - [in] 设备句柄
	deSharpness - [in] 锐化标准(0 - 255)，其它值表示自动取消锐化功能
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnableSharpen(device_handle device, unsigned deSharpness = 128);

/*
描述：
	保边锐化处理功能
参数：
	device - [in] 设备句柄
	deSharpness - [in] 锐化标准(0 - 1000)，其它值表示自动取消锐化功能
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnableSharpenEdgePreserved(device_handle device, unsigned deSharpness = 128);

/*
描述：
	使能伪彩功能
参数：
	device - [in] 设备句柄
	szPColorTemplateFile - [in] 伪彩的模板文件。NULL - 停止使用伪彩
	pcolorDepth - [in] 伪彩的色深。此参数保留。
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnablePColor(device_handle device, char* szPColorTemplateFile, unsigned pcolorDepth);

unsigned __stdcall DXConvertYUVtoRGB(device_handle device, void* pYUVBuf,
							  void* pRGBBuf,
							  long lImgWidth,
							  long lImgHeight,
							  BOOL bInverted,
                              BOOL bInvertColor);

unsigned __stdcall DXConvertYUVtoRGBEx(void* pYUVBuf,
							void* pRGBBuf,
							long lImgWidth,
							long lImgHeight,
							BOOL bInverted,
							BOOL bInvertColor);

/*
描述：
	音频原始数据回调的函数原型
参数：
	buffer - [in] 缓冲区指针
	bufferSize - [out] 获取的编码数据的缓冲区大小（单位：字节）
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
typedef unsigned (__stdcall *fnAudDataCallback)(unsigned char* buffer, unsigned bufferSize, void* context);

/*
描述：
	设置音频原始数据回调的函数
参数：
	device - [in] 设备句柄
	fn - [in] 回调函数指针，NULL - 停止回调
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartAudDataCallback(device_handle device, fnAudDataCallback fn, void* context);

/*
描述：
	停止音频原始数据回调的函数
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopAudDataCallback(device_handle device);

/*
描述：
	设置时间OSD参数的函数
参数：
	device - [in] 设备句柄
	x,y - [in]OSD的位置坐标
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetTimeOSD
(
	/*in*/ device_handle device, 
	/*in*/ int x, 
	/*in*/ int y,  
	/*in*/ int pointSize,
	/*in*/ const char* faceName = "Arial",
	/*in*/ COLORREF color = RGB(0,0,255),
	/*in*/ COLORREF bgcolor = RGB(0, 0, 0),
	/*in*/ BOOL transparent = TRUE
);

/*
描述：
	设置文本OSD参数的函数
参数：
	device - [in] 设备句柄
	x,y - [in]OSD的位置坐标
返回值：
	0 - 成功；失败则返回错误代码
// */							
unsigned __stdcall DXSetTextOSD
(
	/*in*/ device_handle device, 
	/*in*/ int x, 
	/*in*/ int y,
	/*in*/ int TextNO,
	/*in*/ char* osdText,
	/*in*/ int pointSize,
	/*in*/ const char* faceName = "Arial",
	/*in*/ COLORREF color  = RGB(0,0,255),
	/*in*/ COLORREF bgcolor = RGB(0, 0, 0),
	/*in*/ BOOL transparent = TRUE 
);

/*
描述：
	设置图片OSD参数的函数
参数：
	device - [in] 设备句柄
	x,y - [in]OSD的位置坐标
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetPictureOSD
(
	/*in*/ device_handle device, 
	/*in*/ int x, 
	/*in*/ int y,
	/*in*/ int PicNO,
	/*in*/ char* picFileName,
	/*in*/ BOOL transparent = TRUE,
	/*in*/ unsigned char alpha = 255
);

/*
描述：
	设置画线OSD参数的函数
参数：
	device - [in] 设备句柄
	x0,y0,x1,y1 - [in]OSD的位置坐标
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetLineOSD
(
	/*in*/ device_handle device,
	/*in*/ int x0,
	/*in*/ int y0,
	/*in*/ int x1,
	/*in*/ int y1,
	/*in*/ int LineNO,
	/*in*/ int lineSize,
	/*in*/ int lineStyle = style_solid,
	/*in*/ COLORREF color  = RGB(0,0,255),
	/*in*/ unsigned char alpha = 255
);

/*
描述：
	设置画框OSD参数的函数
参数：
	device - [in] 设备句柄
	x,y - [in]OSD的位置坐标
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetRectOSD
(
	/*in*/ device_handle device, 
	/*in*/ int x,
	/*in*/ int y,
	/*in*/ int width,
	/*in*/ int height,
	/*in*/ int RectNO,
	/*in*/ int lineSize,
	/*in*/ int lineStyle = style_solid,
	/*in*/ COLORREF color  = RGB(0,0,255),
	/*in*/ unsigned char alpha = 255
);

/*
描述：
	设置使能OSD参数的函数
参数：
	device - [in] 设备句柄
	osdType - [in]叠加类型
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnOSDDisp
(
	/*in*/ device_handle device, 
	/*in*/ unsigned osdType,       //0表示时间叠加，1表示文本叠加，2表示图片叠加，3表示直线叠加，4表示矩形框叠加
	/*in*/ int number,				/* 叠加编号，当number = -1时为全部 */
	/*in*/ BOOL enable,
		   BOOL bDrawPreviewWin = 0
);

/*
描述：
	从加密芯片用户区读取数据的函数
参数：
	device - [in] 设备句柄
	chPassWord - [in]密码
	chData------[out]读取数据空间
	chLen-------[out]读取数据长度,不超过0x20
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXReadDeviceSerial(device_handle device,unsigned char * chPassWord,
						 unsigned char * chData,  unsigned char& chLen);

//从加密芯片用户区读出数据
/*
描述：
	向加密芯片用户区写入数据的函数
参数：
	device - [in] 设备句柄
	chPassWord - [in]密码
	chData------[in]写入数据空间
	chLen-------[in]写入数据长度,不超过0x20
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXWriteDeviceSerial(device_handle device,unsigned char * chPassWord,
						 unsigned char * chData,  unsigned char chLen);

/*
描述：
	原始视频数据回调的函数原型
参数：
	buffer - [in] 缓冲区指针
	colorSpace - [in] 获取的原始数据的色彩空间类型
	width - [in] 获取的原始数据的像素宽度
	height - [in] 获取的原始数据的像素高度
	bytesWidth - [in] 获取的原始数据的字节宽度
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
typedef unsigned (__stdcall *fnRawVideoCallback)(unsigned char* buffer, unsigned colorSpace,
									   unsigned width, unsigned height, unsigned bytesWidth, void* context);

/*
描述：
	设置原始视频数据回调的函数
参数：
	device - [in] 设备句柄
	fn - [in] 回调函数指针，NULL - 停止回调
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartRawVideoCallback(device_handle device, fnRawVideoCallback fn, void* context);
/*
描述：
	停止原始视频数据回调的函数
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopRawVideoCallback(device_handle device);

/*
描述：
	暂停原始视频数据回调的函数
参数：
	device - [in] 设备句柄
	bPause---[in] true:暂停原始流回调;false:重新开始原始流回调
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXPauseRawVideoCallback(device_handle device, bool bPause);

/*
描述：
	设置原始视频数据回调的函数
参数：
	device - [in] 设备句柄
	bDrawOSD - [in] 是否叠加OSD
	fn - [in] 回调函数指针，NULL - 停止回调
	rc - [in] 视频裁剪区域，NULL - 不裁剪
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartRawVideoCallbackEx(device_handle device, BOOL bDrawOSD, fnRawVideoCallback fn, RECT *rc, void* context);
/*
描述：
	停止原始视频数据回调的函数
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopRawVideoCallbackEx(device_handle device);

/*
描述：
	暂停原始视频数据回调的函数
参数：
	device - [in] 设备句柄
	bPause---[in] true:暂停原始流回调;false:重新开始原始流回调
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXPauseRawVideoCallbackEx(device_handle device, bool bPause);

/*
描述：
	设置父窗口句柄，发送消息，可以与接口DXGetFrameBuffer配合用
参数：
	hPtWnd - [in] 窗口句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetParentWnd(device_handle device, HWND hPtWnd);
/*
描述：
	获取原始视频帧数据,RGB数据流
参数：
	device - [in] 设备句柄
	width - [out] 获取帧的宽度
	height - [out] 获取帧的高度
	buffer - [out] 获取帧缓冲
	filp - [int] 帧是否需要反转
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetBuf(device_handle device, unsigned* width, unsigned* height,unsigned char* buffer,bool filp);
/*
描述：
	获取指定区域的原始视频帧数据到缓冲区
参数：
	device - [in] 设备句柄
	buffer - [in] 指向缓冲区。NULL - 后续参数返回相应的数据，比如，所需缓冲区的大小、颜色空间、视频尺寸
	bufferLen - [in] 指向的缓冲区的大小（单位：字节）
	gotBufferLen - [out] 实际获取的数据的大小（单位：字节）
	colorSpace - [out] 获取的原始数据的色彩空间类型
	width - [out] 获取的原始数据的像素宽度
	height - [out] 获取的原始数据的像素高度
	bytesWidth - [out] 获取的原始数据的字节宽度
	rect - [in] 指定获取数据的区域
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetFrameBuffer(device_handle device, unsigned char* buffer, unsigned bufferLen, unsigned* gotBufferLen = NULL,
									unsigned* colorSpace = NULL, unsigned* width = NULL, unsigned* height = NULL, unsigned* bytesWidth = NULL,
									PRECT rect = NULL);

/*
描述：
	保存原始视频帧数据到 BMP文件
参数：
	szFileName - [in] BMP文件路径
	buffer - [in] 指向缓冲区
	bufferLen - [in] 指向的缓冲区的大小（单位：字节）
	colorSpace - [in] 获取的原始数据的色彩空间类型
	width - [in] 获取的原始数据的像素宽度
	height - [in] 获取的原始数据的像素高度
	bytesWidth - [in] 获取的原始数据的字节宽度
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSaveBMPFile(char* szFileName, unsigned char* buffer, unsigned bufferLen,
								 unsigned colorSpace, unsigned width, unsigned height, unsigned bytesWidth);


/*
描述：
保存原始视频帧数据到 PNG文件
参数：
szFileName - [in] PNG文件路径
buffer - [in] 指向缓冲区
bufferLen - [in] 指向的缓冲区的大小（单位：字节）
colorSpace - [in] 获取的原始数据的色彩空间类型
width - [in] 获取的原始数据的像素宽度
height - [in] 获取的原始数据的像素高度
bytesWidth - [in] 获取的原始数据的字节宽度
返回值：
0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSavePNGFile(char* szFileName, unsigned char* buffer, unsigned bufferLen,
	unsigned colorSpace, unsigned width, unsigned height, unsigned bytesWidth);


/*
描述：
	保存原始视频帧数据到 JPG文件
参数：
	szFileName - [in] JPG文件路径
	buffer - [in] 指向缓冲区
	bufferLen - [in] 指向的缓冲区的大小（单位：字节）
	colorSpace - [in] 获取的原始数据的色彩空间类型
	width - [in] 获取的原始数据的像素宽度
	height - [in] 获取的原始数据的像素高度
	bytesWidth - [in] 获取的原始数据的字节宽度
	quality - [in] JPG文件的画面质量
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSaveJPGFile(char* szFileName, unsigned char* buffer, unsigned bufferLen,
								 unsigned colorSpace, unsigned width, unsigned height, unsigned bytesWidth, unsigned quality);


/*
描述：
	直接抓取原始视频帧数据到 BMP文件
参数：
	device - [in] 设备句柄
	szFileName - [in] BMP文件路径
	rect - [in] 指定获取数据的区域
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSnapToBMPFile(device_handle device, char* szFileName, PRECT rect = NULL);


/*
描述：
直接抓取原始视频帧数据到 PNG文件
参数：
device - [in] 设备句柄
szFileName - [in] PNG文件路径
rect - [in] 指定获取数据的区域
返回值：
0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSnapToPNGFile(device_handle device, char* szFileName, PRECT rect = NULL);


/*
描述：
	直接抓取原始视频帧数据到 JPG文件
参数：
	device - [in] 设备句柄
	szFileName - [in] JPG文件路径
	quality - [in] JPG文件的画面质量
	rect - [in] 指定获取数据的区域
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSnapToJPGFile(device_handle device, char* szFileName, unsigned quality, PRECT rect = NULL);

/*
描述：
	直接抓取原始视频帧数据到 j2k文件
参数：
	device - [in] 设备句柄
	szFileName - [in] j2k文件路径
	rect - [in] 指定获取数据的区域
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSnapToJ2KFile(device_handle device, char* szFileName, PRECT rect = NULL);

/*
描述：
	j2k文件转RGB数据
参数：
	szFileName - [in] j2x文件路径
	pRGB24 - [in out] rgb数据fuffer，需要分配足够大的空间
	nWidth - [out] RGB数据实际宽
	nHeight - [out] RGB数据实际高
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXJ2KToRGB24(char* szFileName, byte* pRGB24, int& nWidth, int& nHeight);

/*
描述：
	j2k文件转BMP文件
参数：
	szFileName - [in] j2x文件路径
	pBMPFileName - [in] bmp文件路径
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXJ2KToBMP(char* szFileName, char* pBMPFileName);


/*
描述：
	翻转视频
参数：
	device - [in] 设备句柄
	flip - [in] TRUE - 启用翻转，FALSE - 禁用翻转
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXFlipVideo(device_handle device, BOOL flip);

/*
描述：
	镜像视频
参数：
	device - [in] 设备句柄
	mirror - [in] TRUE - 启用镜像，FALSE - 禁用镜像
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXMirrorVideo(device_handle device, BOOL mirror);

/*
描述：
    创建预览对象
参数：
	colorspace - [in] 图片缓冲的数据的色彩空间
	width - [in] 图片的宽度（单位：像素）
	height - [in] 图片的高度（单位：像素）
返回值：
	成功则返回图像句柄，否则返回 NULL。可通过 err 获得错误代码
// */
image_handle __stdcall DXCreateBufferImg(unsigned colorspace, unsigned width, unsigned height);

/*
描述：
	更新预览对象到指定的窗体的相应区域
参数：
	img - [in] 预览对象
	hPrevWnd - [in] 预览的窗体
	rect - [in] 预览的区域
	imgbuffer - [in] 预览缓冲数据
	buffersize - [in] 预览缓冲数据大小
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXUpdateImg(image_handle img,HWND hPrevWnd, RECT* rect, unsigned char* imgbuffer, unsigned buffersize);

/*
描述：
	删除预览对象
参数：
	img - [in] 预览对象
返回值：
	无
// */
void __stdcall DXDestroyImg(image_handle img);

/*
描述：
	调节码流的相关属性值
参数：
	device - [in] 设备句柄
	RateType--[in]码流属性的类型,如:drate_color（对比度亮度增强功能）
	pPara - [in]编码器的具体属性值，NULL - 表示停止调节码流的对应属性
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnDataRaterPara(device_handle device, unsigned RateType, void* pPara);

/*
描述：
	调节码流的相关属性值
参数：
	src - [in] 原始流
	dst--[out]输出流
	pixelsPerLines - [in]每一行的像素总数
	width - [in]宽
	height - [in]高
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXYuy2Gray(unsigned char *src, unsigned char *dst, unsigned pixelsPerLines, unsigned width, unsigned height);

/*
描述：
	电子缩放的相关属性值
参数：
	device - [in] 设备句柄
	bEnFScale - [in是否开启缩放
	rect--[in]电子放大局部区域
	enAlogrithm - [in]Scale算法
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXEnFScale(device_handle device,bool bEnFScale, RECT* rect, VidScaleAlogrithm enAlogrithm=VID_SCALE_BICUBIC);

/*
描述：
	原始视频流YUY2的缩放
参数：
	src - [in] 视频源数据缓冲
	srcwidth - [in]视频源宽度
	srcheight--[in]视频源高度
	dst--[out]数据输出缓冲
	dstwidth--[in]数据输出宽度
	dstheight--[in]数据输出高度
	enAlogrithm - [in]Scale算法
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXYuy2Scale(unsigned char* src, unsigned srcwidth, unsigned srcheight, unsigned char* dst, unsigned dstwidth, unsigned dstheight, VidScaleAlogrithm enAlogrithm=VID_SCALE_BICUBIC);

/*
描述：
	原始视频流RGB24的缩放
参数：
	src - [in] 视频源数据缓冲
	srcwidth - [in]视频源宽度,必须为4的倍数
	srcheight--[in]视频源高度
	dst--[out]数据输出缓冲
	dstwidth--[in]数据输出宽度,必须为4的倍数
	dstheight--[in]数据输出高度
	enAlogrithm - [in]Scale算法
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXRGBScale(unsigned char* src, unsigned srcwidth, unsigned srcheight, unsigned char* dst, unsigned dstwidth, unsigned dstheight, VidScaleAlogrithm enAlogrithm=VID_SCALE_BICUBIC);


/*
描述：
	开启网络传输
参数：
    device - [in] 设备句柄
	nPrtclType - [in] 协议类型net_crtsp=1,net_crtmp=2,net_all=0xffff
	stNetPara - [in]具体参数，选择net_crtsp时必须填写port；选择net_crtmp时必须填crtmp_uri；
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartNetTrans(device_handle device, int nPrtclType,  PNetTransPara stNetPara);

/*
描述：
webrtc消息处理函数
参数：
lParam - [in] 消息参数lParam
wParam   - [in] 消息参数wParam
返回值：
0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXWebrtcMsgTreat(void* lParam, void* wParam);

/*
描述： 
	 网络传输音视频流
参数：
    device - [in] 设备句柄
	nPrtclType - [in] 协议类型net_crtsp=1,net_crtmp=2,net_all=0xffff
	DataType - [in] 数据流类型data_vid=0,data_aud=1
	data - [in] 数据流缓冲区
	len - [in] 数据长度
	ms_pts - [in] 时间戳毫秒
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXNetTransData(device_handle device, int nPrtclType, int DataType,unsigned char* data, unsigned len, bool bIskey, LONGLONG ms_pts );

/*
描述： 
	 网络传输MP4录像文件
参数：
    device - [in] 设备句柄
	nPrtclType - [in] 协议类型net_crtsp=0,net_crtmp=1,net_all=2
	szFileName - [in] MP4录像文件名
	bAudio - [in] 是否播放音频
	timeBegin - [in] 开始时间（毫秒）
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXNetTransMP4File(device_handle device, int nPrtclType, const char *szFileName, bool bAudio, LONGLONG timeBegin);

/*
描述： 
	 关闭网络传输
参数：
    device - [in] 设备句柄
	nPrtclType - [in] 协议类型net_crtsp=1,net_crtmp=2,net_all=0xffff
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopNetTrans(device_handle device, int nPrtclType );

/*
描述： 
	 窄字符转换为宽字符
参数：
    
	lpcszStr - [in] 窄字符串内存空间
	lpwszStr - [in] 宽字符串内存空间
	isize - [in]宽字符串内存大小
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXmByteTOwChar(const char* lpcszStr, wchar_t* lpwszStr, unsigned isize);

/*
描述： 
	 宽字符转换为窄字符
参数：
    lpcwszStr - [in] 宽字符串内存空间
	lpszStr - [in] 窄字符串内存空间
	isize - [in]窄字符串内存大小
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXwCharTOmByte(const wchar_t* lpcwszStr, char* lpszStr, unsigned isize);

/*
描述： 
	 宽字符转换为UTF8字符
参数：
    lpcwszStr - [in] 宽字符串内存空间
	lpszStr - [in] UTF8字符串内存空间
	isize - [in]UTF8字符串内存大小
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXwCharTOUTF8(const wchar_t* lpcwszStr, char* lpszStr, int isize);

/*
描述： 
	视频旋转90度
参数：
    pDes - [out]视频目的地址
    pSrc - [in]视频源地址
	nWidth - [in]视频宽度
	nHeight - [in]视频高度
	bRight - [in]true顺时针,false逆时针
	nColorspace - [in]颜色空间，目前只支持cs_rgb24和_device_tag
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXYUYRotate90(char *pDes,char *pSrc,unsigned nWidth,unsigned nHeight,bool bRight,unsigned nColorspace);

/*
描述： 
	 设置高清视频RGB值
参数：
    device - [in] 设备句柄
	nGainType - [in]  R:0  G:1  B:2
	chValue - [in] 具体的值
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetGainHD(device_handle device,unsigned char nGainType,unsigned char chValue); 
/*
描述：
	高清视频镜像
参数：
	device - [in] 设备句柄
	mirror - [in] TRUE - 启用镜像，FALSE - 禁用镜像
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetMirrorHD(device_handle device, BOOL mirror);

/*
描述：
	高清翻转视频
参数：
	device - [in] 设备句柄
	flip - [in] TRUE - 启用翻转，FALSE - 禁用翻转
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetFilpHD(device_handle device, BOOL flip);

/*
描述：
	获取AHD EQ增益
参数：
	device - [in] 设备句柄
	eqType - [in] 参数类型
					ahd_eqgain_1，ahd_eqgain_2等
	eqVaule - [out] 参数值指针
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetEQGainAHD(device_handle device, int eqType, unsigned char *eqVaule);

/*
描述：
	设置AHD EQ增益
参数：
	device - [in] 设备句柄
	eqType - [in] 参数类型
					ahd_eqgain_1，ahd_eqgain_2等
	eqVaule - [in] 参数值
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSetEQGainAHD(device_handle device, int eqType, unsigned char eqVaule);

/*
描述：
	设置原始视频数据回调的函数
参数：
	device - [in] 设备句柄
	fn - [in] 回调函数指针，NULL - 停止回调
	rct - [in] 限定原始流的出流区域
	bInvertColor - [in]是否反色
	context - [in] 回调函数的上下文
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartRawVideoCallbackHD(device_handle device, fnRawVideoCallback fn,RECT *rct,BOOL bInvertColor, void* context);

/*
描述：
	创建设备属性页
参数：
	device - [in] 设备句柄
	nPropertyType - [in] 属性页类型，取值为PropertyPage_VideoCapureFilter等
	hWndOwner - 拥有属性页对话框的窗口句柄
	x - 属性页相对于hWndOwner的客户区坐标
	y - 属性页相对于hWndOwner的客户区坐标
	szCaption - 属性页对话框的窗口标题
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXCreatePropertyPage(device_handle device, int nPropertyType, HWND hWndOwner, unsigned x, unsigned y, const char *szCaption);

/*
描述：
	创建NDI发送实例
参数：
	device - [in] 设备句柄
	szSourceName - [in] NDI视频源名字
	szGroupName - [in] NDI组名，NULL表示不设置组名
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXCreateNDIInstance(device_handle device, const char *szInstanceName, const char *szGroupName);

/*
描述：
	NDI发送原始音频数据
参数：
	device - [in] 设备句柄
	buffer - [in] 音频数据缓冲区指针
	bufferSize - [in] 音频数据缓冲区大小（单位：字节）
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSendNDIAudioData(device_handle device, unsigned char* buffer, unsigned bufferSize);

/*
描述：
	NDI发送原始视频数据
参数：
	device - [in] 设备句柄
	buffer - [in] 视频数据缓冲区指针
	colorSpace - [in] 视频数据的色彩空间类型
	width - [in] 视频数据的像素宽度
	height - [in] 视频数据的像素高度
	bytesWidth - [in] 视频数据行字节宽度
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXSendNDIVideoData(device_handle device, unsigned char* buffer, unsigned colorSpace, unsigned width, unsigned height, unsigned bytesWidth);

/*
描述：
	销毁NDI发送实例
参数：
	device - [in] 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXDestoryNDIInstance(device_handle device);

/*
描述：
	复位ADV
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXResetADV(void);

/*
描述：
	复位UVC设备
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXResetUVCDevice(void);

/*
描述：
	复位ADV
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXGetDeviceSN(device_handle device, unsigned char * readDataOut);

/*
描述：
	AI检测结果回调函数
参数：
	buffer - RGB数据
	width -  画面宽
	height - 画面高
	pAIExamRes - AI检测结果
	pContext - 上下文句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
typedef unsigned (__stdcall *AIExamCallback)(unsigned char* buffer/*RGB24*/, unsigned width, unsigned height, AIExamResult* pAIExamRes, void* context);

/*
描述：
	开启AI检测功能
参数：
	device - 设备句柄
	nAIExamType -  AI检测类型，目前只有 1011：乳腺筛查
	nExamFPS - 每秒检测帧数，一般不超过8帧，按经验，2-3帧可以满足需求
	nDrawAIResultType - 画AI检测结果的类型，0：不画结果，1：画结果到预览画面，2：画结果到采集数据，此时预览、录像都会有画AI检测结果
	bDrawAIResultInCallbackBuf - 是否在回调数据上画检测结果
	pfunc - 回调函数,可为空,
	pContext - 上下文句柄, 可为空
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStartAIExam(device_handle device, int nAIExamType, int nExamFPS, int nDrawAIResultType, bool bDrawAIResultInCallbackBuf, AIExamCallback pfunc, void* pContext);

/*
描述：
	停止AI检测功能
参数：
	device - 设备句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXStopAIExam(device_handle device);

/*
描述：
	创建Dicom客户端对象
参数：
	chServerAddr - 服务器地址，可以为IP或者域名
	uiServerPort - 服务器侦听端口
	chServerApplicationTitle - aec 服务端应用名
	pDCMHandel - [out] 句柄指针,创建成功则非空
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXCreateDicomWorkStation(const char* chServerAddr, unsigned int uiServerPort, const char* chServerApplicationTitle, DCM_HANDLE* pDCMHandel);

/*
描述：
	创建Dicom客户端对象
参数：
	chServerAddr - 服务器地址，可以为IP或者域名
	uiServerPort - 服务器侦听端口
	chServerApplicationTitle - aec 服务端应用名
	chClientApplicationTitle - aet 客户端应用名
	pDCMHandel - [out] 句柄指针,创建成功则非空
返回值：
	0 - 成功；失败则返回错误代码
// */
unsigned __stdcall DXCreateDicomWorklistConnection(const char* chServerAddr, unsigned int uiServerPort, const char* chServerApplicationTitle, const char* chClientApplicationTitle, DCM_HANDLE* pDCMHandel);

/*
描述：
	启动Dicom客户端对象
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStartDicomWorkStation(DCM_HANDLE pDCMHandel);

/*
描述：
	停止Dicom客户端对象
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStopDicomWorkStation(DCM_HANDLE pDCMHandel);

/*
描述：
	销毁Dicom客户端对象
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXDestoryDicomWorkStation(DCM_HANDLE pDCMHandel);

/*
描述：
	销毁Dicom客户端对象
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXDestoryDicomWorklistConnection(DCM_HANDLE pDCMHandel);

/*
描述：
	开始查询
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	chClientApplicationTitle - [in] aet 客户端应用名
	chOutPutFolder - [in] 查询结果输出文件路径
	chOutputXmlFilePath - [in] 查询结果输出xml文件名
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStartDicomQuery(DCM_HANDLE pDCMHandel, const char* chClientApplicationTitle, const char* chOutPutFolder, const char* chOutputXmlFilePath);

/*
描述：
	中断查询
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStopDicomQuery(DCM_HANDLE pDCMHandel);

/*
描述：
	开始下载，下载查询接口获得的查询结果对应图像文件
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	chClientApplicationTitle - [in] aet 客户端应用名
	chDownloadFolder - [in] 下载文件输出路径
	DownloadStatusFunc - [in] 下载状态反馈回调函数
	pContext - [in] 回调函数上下文句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStartDicomDownload(DCM_HANDLE pDCMHandel, const char* chClientApplicationTitle, const char* chDownloadFolder, LoadStatusFunc DownloadStatusFunc, void* pContext);

/*
描述：
	中断下载
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStopDicomDownload(DCM_HANDLE pDCMHandel);

/*
描述：
	开始下载，下载指定study UID对应图像文件
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	chClientApplicationTitle - [in] aet 客户端应用名
	chStudyUID - [in] study instance ID
	chDownloadFolder - [in] 下载文件输出路径
	DownloadStatusFunc - [in] 下载状态反馈回调函数
	pContext - [in] 回调函数上下文句柄
返回值：
0 - 成功；失败则返回错误代码
// */
int __stdcall DXStartDicomDownloadByStudyUID(DCM_HANDLE pDCMHandel, const char* chClientApplicationTitle, const char* chStudyUID, const char* chDownloadFolder, LoadStatusFunc DownloadStatusFunc, void* pContext);

/*
描述：
	开始下载，下载指定Patient ID对应图像文件
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	chClientApplicationTitle - [in] aet 客户端应用名
	chPatientID - [in] Patient ID
	chDownloadFolder - [in] 下载文件输出路径
	DownloadStatusFunc - [in] 下载状态反馈回调函数
	pContext - [in] 回调函数上下文句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStartDicomDownloadByPatientID(DCM_HANDLE pDCMHandel, const char* chClientApplicationTitle, const char* chPatientID, const char* chDownloadFolder, LoadStatusFunc DownloadStatusFunc, void* pContext);

/*
描述：
	开始上传，上传指定文件夹内所有图像文件
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	chClientApplicationTitle - [in] aet 客户端应用名
	chUploadFolder - [in] 指定上传文件夹
	UploadStatusFunc - [in] 上传状态反馈回调函数
	pContext - [in] 回调函数上下文句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStartdicomFolderUpload(DCM_HANDLE pDCMHandel, const char* chClientApplicationTitle, const char* chUploadFolder, LoadStatusFunc UploadStatusFunc, void* pContext);

/*
描述：
	停止上传，
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStopDicomUpload(DCM_HANDLE pDCMHandel);

/*
描述：
	开始上传，上传指定图像文件
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	chClientApplicationTitle - [in] aet 客户端应用名
	chUploadFile - [in] 上传图像文件名
	UploadStatusFunc - [in] 上传状态反馈回调函数
	pContext - [in] 回调函数上下文句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStartdicomFileUpload(DCM_HANDLE pDCMHandel, const char* chClientApplicationTitle, const char* chUploadFile, LoadStatusFunc UploadStatusFunc, void* pContext);

/*
描述：
	设置查询条件
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	nQueryLevel - [in] Dicom查询级别 0：DICOM_QUERY_LEVEL_PATIENT 1：DICOM_QUERY_LEVEL_STUDY 2：DICOM_QUERY_LEVEL_SERIES 3：DICOM_QUERY_LEVEL_IMAGE
	chPatientName - [in] Patient名称
	chPatientID - [in] Patient ID
	chStudyInstanceUID - [in] 检查UID
	chStudyDate - [in] 检查日期
	chStudyTime - [in] 检查时间
	chReferringPhysicianName - [in] 检查医生
	chStudyID - [in] 检查ID
	chAccessionNumber - [in] 登记号
	chStudyDescription - [in] 检查描述信息
	chReadingPhysiciansName - [in] 阅读医生名
	chModality - [in] 检查设备
	SeriesInstanceUID - [in] 序列UID
	PerformingPhysicianName - [in] 诊断医生
	InstitutionalDepartmentName - [in] 检查机构名
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXSetDicomOperationCondition(DCM_HANDLE pDCMHandel
	, unsigned int nQueryLevel
	, const char* chPatientName
	, const char* chPatientID
	, const char* chStudyInstanceUID
	, const char* chStudyDate
	, const char* chStudyTime
	, const char* chReferringPhysicianName
	, const char* chStudyID
	, const char* chAccessionNumber
	, const char* chStudyDescription
	, const char* chReadingPhysiciansName
	, const char* chModality
	, const char* SeriesInstanceUID
	, const char* PerformingPhysicianName
	, const char* InstitutionalDepartmentName);

/*
描述：
	开始查询工作表
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
	chModalityApplicationTitle - [in] aet 客户端应用名
	chWlFileName - [in] 查询条件wl文件名
	chOutPutFolder - [in] 查询结果输出文件路径
	chOutputXmlFilePath - [in] 查询结果输出xml文件名
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXstartDicomWorklistQuery(DCM_HANDLE pDCMHandel, const char* chModalityApplicationTitle, const char* chWlFileName, const char* chOutPutFolder, const char* chOutputXmlFilePath);

/*
描述：
	停止查询工作表
参数：
	pDCMHandel - [in] Dicom客户端对象句柄
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXStopDicomWorklistQuery(DCM_HANDLE pDCMHandel);

/*
描述：
	创建dicom序列
参数：
	pSeriesHandle - [out] 序列句柄指针
	chDcmFileName - [in] 序列文件名称
	nImgWidth - [in] 图像宽度
	nImgHeight - [in] 图像高度
 	fFrameRate - [in] 图像帧率
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXCreateDicomSeriesImage(SERIES_HANDLE* pSeriesHandle, const char* chDcmFileName, unsigned int nImgWidth, unsigned int nImgHeight, float fFrameRate);

/*
描述：
	销毁dicom序列，释放序列对象 并且保存文件
参数：
	pSeriesHandle - [out] 序列句柄指针
	chDcmFileName - [in] 序列文件名称
	nImgWidth - [in] 图像宽度
	nImgHeight - [in] 图像高度
	fFrameRate - [in] 图像帧率
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXDestoryDicomSeriesImage(SERIES_HANDLE pSeriesHandle);

/*
描述：
	添加jpg文件到dicom序列，目前仅支持jpg文件
参数：
	pSeriesHandle - [out] 序列句柄指针
	chJpgFilePath - [in] 序列文件名称
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXAddDicomSeriesImageJpg(SERIES_HANDLE pSeriesHandle, const char* chJpgFilePath);

/*
描述：
	DCM文件转换成jpg文件
参数：
	chSrcDcmFilePath - [in] dcm文件名
	chDestJpgFilePath - [in] jpg文件名，全路径，不带“.jpg”扩展名，在转换过程中由函数自动添加
	nQuality 
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXDcm2Jpg(const char* chSrcDcmFilePath, const char* chDestJpgFilePath, unsigned int nQuality);

/*
描述：
	DCM文件转换成bmp文件
参数：
	chSrcDcmFilePath - [in] dcm文件名
	chDestBmpFilePath - [in] bmp文件名，全路径，不带“.bmp”扩展名，在转换过程中由函数自动添加
返回值：
0 - 成功；失败则返回错误代码
// */
int __stdcall DXDcm2Bmp(const char* chSrcDcmFilePath, const char* chDestBmpFilePath);

/*
描述：
	bmp文件转换成DCM文件
参数：
	chSrcBmpFilePath - [in] bmp文件名
	chDestDcmFilePath - [in] dcm文件名
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXBmp2Dcm(const char* chSrcBmpFilePath, const char* chDestDcmFilePath);

/*
描述：
	jpg文件转换成DCM文件
参数：
	chSrcJpgFilePath - [in] jpg文件名
	chDestDcmFilePath - [in] dcm文件名
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXJpg2Dcm(const char* chSrcJpgFilePath, const char* chDestDcmFilePath);

/*
描述：
	获取dcm文件信息
参数：
	chDcmFilePath - [in] dcm文件名
	strPatientName - [out] Patient名称
	strPatientID - [out] Patient ID
	strStudyInstanceUID - [out] 检查UID
	strStudyDate - [out] 检查日期
	strStudyTime - [out] 检查时间
	strReferringPhysicianName - [out] 检查医生
	strStudyID - [out] 检查ID
	strAccessionNumber - [out] 登记号
	strStudyDescription - [out] 检查描述
	strReadingPhysiciansName - [out] 阅读医生
	strModality - [out] 检查设备
	strSeriesInstanceUID - [out] 序列UID
	strPerformingPhysicianName - [out] 诊断医生
	trInstitutionalDepartmentName - [out] 检查机构名
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXGetDcmInfo(const char* chDcmFilePath
	, std::string &strPatientName
	, std::string &strPatientID
	, std::string &strStudyInstanceUID
	, std::string &strStudyDate
	, std::string &strStudyTime
	, std::string &strReferringPhysicianName
	, std::string &strStudyID
	, std::string &strAccessionNumber
	, std::string &strStudyDescription
	, std::string &strReadingPhysiciansName
	, std::string &strModality
	, std::string &strSeriesInstanceUID
	, std::string &strPerformingPhysicianName
	, std::string &strInstitutionalDepartmentName);

/*
描述：
	设置dcm文件信息
参数：
	chDcmFilePath - [in] dcm文件名
	strPatientName - [in] Patient名称
	strPatientID - [in] Patient ID
	trReferringPhysicianName - [in] 检查医生
	strAccessionNumber - [in] 登记号
	strStudyDescription - [in] 检查描述
	strReadingPhysiciansName - [in] 阅读医生
	strModality - [in] 检查设备
	strPerformingPhysicianName - [in] 诊断医生
	strInstitutionalDepartmentName - [in] 检查机构名
返回值：
	0 - 成功；失败则返回错误代码
// */
int __stdcall DXSetDcmInfo(const char* chDcmFilePath
	, const char* strPatientName
	, const char* strPatientID
	, const char* strReferringPhysicianName
	, const char* strAccessionNumber
	, const char* strStudyDescription
	, const char* strReadingPhysiciansName
	, const char* strModality
	, const char* strPerformingPhysicianName
	, const char* strInstitutionalDepartmentName);
}
#endif // __DXMEDIACAP_2011__
