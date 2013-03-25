Name:       test-package
Summary:    Test package for the git-buildpackage OBS source service
Version:    0.1
Release:    0
Group:      Development/Libraries
License:    GPL-2.0
Source:     %{name}-%{version}.tar.bz2

%description
Dummy package for testing the git-buildpackage OBS source service.


%prep
%setup -q


%build
TEST_PKG_VERSION=%{version} make


%install
make install


%files
%defattr(-,root,root,-)
%doc README VERSION
