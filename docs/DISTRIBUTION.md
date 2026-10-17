# 공개 및 재배포

## 공개 범위

프로젝트 자체 소스는 MIT입니다. `LICENSE`를 유지하세요. 현재 준비한 공개 대상은
**Git 이력 없는 소스 ZIP**입니다. 기존 로컬 `.git`을 지우거나 변경하지 않고 현재 파일만
추출합니다. 개인 이메일은 공개 허용 범위이며, 쿠키·자격증명·음원·로그·빌드 결과는 제외합니다.
GitHub에 업로드하거나 저장소를 생성하는 동작은 수행하지 않습니다.

```bash
python scripts/release_check.py
python scripts/export_public_source.py
```

결과는 `dist/YTMusicDownloader-source.zip`입니다. 작업 파일과 Git 인덱스의 텍스트를 검사하고,
검사한 현재 파일을 ZIP으로 만듭니다. 과거 커밋과 Git 메타데이터는 포함하지 않습니다.
패턴 검사는 모든 종류의 비밀정보 부재를 보증하지 않습니다. 공개 시에는 기존 저장소의
전체 폴더가 아니라 이 소스 ZIP의 내용을 새 저장소에 사용하세요.

## 확보한 배포 자료

- FFmpeg 8.1.2, LAME 3.100의 원본 소스와 acoustid/ffmpeg-build v8.1.2-1 빌드 레시피.
- Qt 6.12.0의 qtbase, qtsvg, qtimageformats와 PySide/Shiboken 6.12.0 공식 소스.
- 위 아카이브의 SHA-256, 출처 URL, Qt 제3자 귀속 자료와 원문 라이선스.
- 실제 Windows 빌드 환경의 패키지 버전 목록: `requirements-build-windows.lock`.
- Qt 6.11.2로 교체한 별도 onefile 빌드와 EXE 단독 실행 검증 기록.

큰 대응 소스 아카이브는 Git 소스 ZIP에 넣지 않고 `release-materials/sources/`에 보관합니다.
이 자료를 별도 ZIP으로 묶으려면 다음 명령을 실행합니다.

```bash
python scripts/export_dependency_sources.py
```

결과는 `dist/YTMusicDownloader-dependency-sources.zip`입니다. 포함된 `SOURCES.json`이
각 아카이브의 출처와 해시를 기록하며, 생성 후 ZIP 안의 파일 해시까지 다시 검사합니다.
이 ZIP은 소스 자료이며 **바이너리 재배포 의무 전체를 충족했다는 인증서가 아닙니다**.

FFmpeg 자료는 다음과 같이 다시 준비할 수 있습니다. 다운로드는 파일별 최대 120초,
20초간 전송 정체 시 중단하며, 고정 해시와 일치하지 않으면 사용하지 않습니다.

```bash
python scripts/prepare_ffmpeg.py --download
```

Qt 소스의 공식 URL과 체크섬은 `scripts/collect_qt_notices.py`의 `SOURCES` 및
`licenses/qt-6.12.0/provenance.json`에 있습니다. 해당 아카이브를
`release-materials/sources/`에 확보한 뒤 `python scripts/collect_qt_notices.py`로
원문 고지를 재수집합니다. Qt 소스 아카이브의 버전 일치는 확인했지만, 배포 휠의 정확한
빌드 설정과 별도 패치까지 재현한 것은 아닙니다.

## 로컬 빌드

```bash
python -m pip install -r requirements-build-windows.lock
python -m pip install -e . --no-deps --no-build-isolation
python scripts/prepare_ffmpeg.py --download
python scripts/build_desktop.py --clean
python scripts/verify_onefile.py dist/YTMusicDownloader.exe --output build/public-prep-verification
```

이 버전 목록은 검증한 Windows x86_64/Python 3.12.14 환경의 기록입니다. 휠 해시 잠금이나
모든 운영체제에 대한 호환 보증은 아닙니다. macOS/Linux는 해당 OS에서 별도로 빌드합니다.
빌드는 300초, EXE 단독 검증은 75초를 넘기면 하위 프로세스를 종료합니다.

패키지는 개발용 imageio-ffmpeg/Gyan 바이너리 대신 검증된 오디오 전용 FFmpeg를 사용합니다.
Windows 빌드 PATH는 Python과 시스템 폴더로 제한하여 다른 앱의 DLL 유입을 막습니다.
이 QWidget 앱에서 사용하지 않는 오래된 `opengl32sw.dll`은 포함하지 않습니다.

Windows 실행에는 EXE 하나면 되지만, 바이너리를 공개할 때 소스·고지·재빌드 자료를
별도로 함께 제공해야 할 수 있습니다. **단일 EXE 실행과 단일 파일만 공개 배포하는 것은 다릅니다.**

## Qt 교체 검증

사용자는 LGPL 라이브러리를 변경하고, 변경된 라이브러리로 앱을 사용하며, 해당 변경의
디버깅을 위해 역공학할 권리를 보유합니다. 앱의 MIT 라이선스는 이를 제한하지 않습니다.

현재 검증은 원래 환경을 유지한 채 PySide6-Essentials/Shiboken 6.11.2를 별도 디렉터리에
설치하고, `PYTHONPATH`를 그 디렉터리로 지정하여 앱을 onefile로 다시 빌드한 것입니다.
실제 EXE의 Qt 버전과 포함된 DLL 해시가 교체 라이브러리와 일치함을 확인했습니다.
이는 **대체 Qt 스택으로 앱을 재조립할 수 있다는 검증**이며, Qt 소스를 수정하고 컴파일하는
전체 과정의 성공을 뜻하지 않습니다. 기록은 `build/qt-relink/`에 있습니다.

수정한 Qt를 사용하는 재빌드 절차:

1. 공개된 앱 소스를 새 폴더에 풀고 지원 Python으로 가상환경을 만듭니다.
2. 빌드 의존성과 앱을 설치한 다음, 제공된 Qt/PySide 소스와 해당 버전의 공식 빌드 지침으로
   수정한 Qt/PySide/Shiboken을 같은 ABI/아키텍처로 빌드합니다.
3. 가상환경의 Qt/PySide/Shiboken을 함께 교체하거나, 검증된 별도 디렉터리를 `PYTHONPATH`로
   지정합니다. 서로 다른 버전의 바인딩과 Qt DLL을 섞지 않습니다.
4. `python scripts/build_desktop.py --clean`으로 재조립하고 패키지 검증을 실행합니다.
   교체 후 일반 의존성 설치 명령으로 해당 라이브러리를 다시 덮어쓰지 않습니다.

공식 지침: [Qt for Python 소스 빌드](https://doc.qt.io/qtforpython-6/building_from_source/index.html).

## 바이너리 공개 제한

```bash
python scripts/release_check.py --binary
python scripts/build_desktop.py --release
```

두 명령은 다음 사항이 해결될 때까지 의도적으로 실패합니다.

- 공식 Qt/PySide 버전별 소스와 실제 휠의 정확한 빌드 설정·추가 패치 연결은 미검증입니다.
- FFmpeg 레시피의 MinGW/GCC 배포 패키지가 정확한 패치 버전으로 고정되지 않았고,
  Python에 포함된 libffi DLL의 정확한 리비전도 확인되지 않았습니다.
- 네이티브 런타임 재배포 조건의 최종 대조, macOS/Linux 실기기 검증은 완료되지 않았습니다.

고지 파일만으로 이 항목들을 완료 처리하지 않습니다. 정확한 공급망 자료를 확보하거나
고정된 도구로 직접 재빌드해 검증해야 합니다. 이 환경에는 해당 네이티브 빌드 도구와
macOS 실행 환경이 없어 전체 소스 빌드를 검증하지 않았습니다. 이는 사용자에게 단순
체크박스 확인을 맡기는 항목이 아니라, 별도의 기술적 검증이 필요한 제한입니다.
CI는 테스트와 로컬용 빌드만 수행하며 아티팩트나 Releases를 게시하지 않습니다.

## 콘텐츠와 약관

이 앱은 YouTube/Google의 공식 제품이 아닙니다. MIT 라이선스는 음악의 저작권이나
서비스 접근 권한을 부여하지 않습니다. 허용되지 않은 다운로드·자동 접근, 보호 조치 우회,
타인의 쿠키 사용 및 음원 재배포를 권장하지 않습니다.

- [YouTube 이용약관](https://www.youtube.com/static?template=terms)
- [FFmpeg 라이선스 안내](https://ffmpeg.org/legal.html)
- [Qt LGPL 안내](https://www.qt.io/faq/qt-open-source-licensing)

이 문서와 자동 검사는 법률 자문이나 모든 관할의 적법성 보증이 아닙니다.
