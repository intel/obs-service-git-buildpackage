# Set to 0 if "normal release"
%define pre_release 0

%if 0%{?pre_release}
%define release_prefix 0pre%{pre_release}.
%endif

Name:           obs-service-git-buildpackage
License:        GPL-2.0+
Group:          Development/Tools/Building
Summary:        Get sources from a repository managed with the git-buildpackage suite
Version:        0.7
Release:        %{?release_prefix}%{?opensuse_bs:<CI_CNT>.<B_CNT>}%{!?opensuse_bs:1}
URL:            http://www.tizen.org
Source:         %{name}-%{version}.tar.bz2
Requires:       git-buildpackage
Requires:       git-buildpackage-rpm
Requires:       gbp-repocache = %{version}-%{release}
BuildRequires:  python
BuildRequires:  python-setuptools
%if 0%{?do_unittests}
BuildRequires:  python-coverage
BuildRequires:  python-nose
BuildRequires:  git-buildpackage-rpm
%endif
BuildArch:      noarch

%description
This is a source service for openSUSE Build Service.

It supports cloning/updating repo from git and exporting sources and packaging
files that are managed with git-buildpackage tools.


%package utils
Summary:    Utility fuctions for the GBP OBS source service
Group:      Development/Tools/Building
Requires:   python >= 2.6
Requires:   gbp-repocache = %{version}

%description utils
This package contains generic utility functions for the git-buildpackage OBS
source service.


%package -n gbp-repocache
Summary:    Git repository cache API
Group:      Development/Tools/Building
Requires:   git-buildpackage-common

%description -n gbp-repocache
This package provides an implementation and python API of a Git repository
cache.


%prep
%setup


%build
%{__python} setup.py build


%if 0%{?do_unittests}
%check
GIT_AUTHOR_EMAIL=rpmbuild@example.com GIT_AUTHOR_NAME=rpmbuild \
    GIT_COMMITTER_NAME=$GIT_AUTHOR_NAME GIT_COMMITTER_EMAIL=$GIT_AUTHOR_EMAIL \
    %{__python} setup.py nosetests
%endif


%install
%{__python} setup.py install --skip-build --root=%{buildroot} --prefix=%{_prefix}
rm -rf %{buildroot}%{python_sitelib}/*info


%files
%defattr(-,root,root,-)
%doc COPYING DEPLOYMENT
%dir /usr/lib/obs
%dir /usr/lib/obs/service
/usr/lib/obs/service/*
%{python_sitelib}/obs_service_gbp
%dir %{_sysconfdir}/obs
%dir %{_sysconfdir}/obs/services
%config %{_sysconfdir}/obs/services/*

%files utils
%defattr(-,root,root,-)
%doc COPYING
%{python_sitelib}/obs_service_gbp_utils

%files -n gbp-repocache
%defattr(-,root,root,-)
%doc COPYING
%{python_sitelib}/gbp_repocache
