%define do_unittests 0

Name:           obs-service-git-buildpackage
License:        GPL-2.0+
Group:          Development/Tools/Building
Summary:        Get sources from a repository managed with the git-buildpackage suite
Version:        0.1
Release:        0
URL:            http://www.tizen.org
Source:         %{name}-%{version}.tar.bz2
Requires:       git-buildpackage-rpm
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


%prep
%setup


%build
%{__python} setup.py build


%if 0%{?do_unittests}
%check
%{__python} setup.py nosetests
%endif


%install
%{__python} setup.py install --skip-build --root=%{buildroot} --prefix=%{_prefix}
rm -rf %{buildroot}%{python_sitelib}/*info


%files
%defattr(-,root,root,-)
%doc COPYING
%dir /usr/lib/obs
%dir /usr/lib/obs/service
/usr/lib/obs/service/*
%{python_sitelib}/obs_service_gbp
